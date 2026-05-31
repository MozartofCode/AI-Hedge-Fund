"""
FX Technician — multi-timeframe technical analysis on currency pairs.
Uses yfinance (EURUSD=X etc.) — no API key needed.

Signals: EMA 20/50/200, RSI, MACD, ATR, Bollinger Bands (daily + weekly).
Cached 10 minutes per pair.
"""
import json
import math
import time
import numpy as np
import pandas as pd

from backend.agents.base_agent import call_claude
from backend.data.forex_client import get_pair_history, get_current_rate

_cache: dict = {}
_CACHE_TTL = 600   # 10 minutes

SYSTEM_PROMPT = """You are the FX Technician on an AI forex trading committee.
Return ONLY valid JSON — no markdown, no explanation:
{
  "action": "BUY" | "SELL" | "HOLD",
  "confidence": 0.0-1.0,
  "rationale": "1 plain-English sentence about what the chart shows (e.g. 'The euro is in a clear uptrend against the dollar, holding above all major moving averages with improving momentum.')",
  "suggested_position_size_pct": 0-8,
  "momentum_score": 0.0-1.0
}

BUY = go long the base currency (e.g. BUY EURUSD = buy EUR, sell USD).
SELL = go short the base currency (sell EUR, buy USD).

EMA alignment:
- EMA20 > EMA50 > EMA200 = full_bullish → BUY with high confidence
- EMA20 < EMA50 < EMA200 = full_bearish → SELL with high confidence
- Mixed = wait for clarity → HOLD or low-confidence BUY/SELL

RSI: 40-65 in uptrend = healthy momentum. >70 = overbought (reduce confidence). <30 = oversold.
MACD: bullish crossover (MACD > signal) = buy signal. Bearish = sell signal.
ATR: measures daily volatility — high ATR = wide stop needed, reduce position size.
Weekly EMA alignment overrides daily when they conflict.

momentum_score: 1.0 = strong confirmed uptrend, 0.0 = strong downtrend, 0.5 = neutral."""


def _safe_float(val, decimals: int = 6) -> float | None:
    try:
        f = float(val)
        return round(f, decimals) if not (math.isnan(f) or math.isinf(f)) else None
    except Exception:
        return None


def _clean_nans(obj):
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: _clean_nans(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_nans(v) for v in obj]
    return obj


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _rsi(s: pd.Series, n: int = 14) -> float | None:
    delta = s.diff().dropna()
    if len(delta) < n:
        return None
    gain = delta.clip(lower=0).rolling(n).mean()
    loss = (-delta.clip(upper=0)).rolling(n).mean()
    rs   = gain.iloc[-1] / loss.iloc[-1] if loss.iloc[-1] != 0 else 100
    return _safe_float(100 - (100 / (1 + rs)), 2)


def _macd_signal(s: pd.Series) -> str:
    """Returns 'bullish', 'bearish', or 'neutral'."""
    try:
        macd  = _ema(s, 12) - _ema(s, 26)
        signal = _ema(macd, 9)
        return "bullish" if macd.iloc[-1] > signal.iloc[-1] else "bearish"
    except Exception:
        return "neutral"


def _atr(df: pd.DataFrame, n: int = 14) -> float | None:
    try:
        high = df["High"]; low = df["Low"]; close = df["Close"]
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low  - close.shift()).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(n).mean().iloc[-1]
        return _safe_float(atr)
    except Exception:
        return None


def _ema_alignment(c: pd.Series) -> str:
    """Return EMA alignment label given a Close price series."""
    if len(c) < 200:
        return "insufficient_data"
    e20  = _safe_float(_ema(c, 20).iloc[-1])
    e50  = _safe_float(_ema(c, 50).iloc[-1])
    e200 = _safe_float(_ema(c, 200).iloc[-1]) if len(c) >= 200 else None
    if None in (e20, e50, e200):
        return "insufficient_data"
    if e20 > e50 > e200:
        return "full_bullish"
    if e20 < e50 < e200:
        return "full_bearish"
    if e20 > e200:
        return "bullish"
    return "bearish"


def get_vote(pair: str) -> dict:
    if pair in _cache:
        data, ts = _cache[pair]
        if time.time() - ts < _CACHE_TTL:
            return data

    try:
        df_d  = get_pair_history(pair, "2y",  "1d")
        df_w  = get_pair_history(pair, "5y",  "1wk")

        if df_d.empty or len(df_d) < 30:
            raise ValueError(f"Insufficient daily history for {pair}")

        c = df_d["Close"].dropna()
        current_rate = _safe_float(c.iloc[-1])

        # ── Daily indicators ──────────────────────────────────────────────────
        ema20  = _safe_float(_ema(c, 20).iloc[-1])
        ema50  = _safe_float(_ema(c, 50).iloc[-1])
        ema200 = _safe_float(_ema(c, 200).iloc[-1]) if len(c) >= 200 else None

        rsi    = _rsi(c)
        macd   = _macd_signal(c)
        atr    = _atr(df_d)
        atr_pct = _safe_float(atr / current_rate * 100, 3) if (atr and current_rate) else None

        # Bollinger Band position
        bb_pos = None
        try:
            sma20 = c.rolling(20).mean()
            std20 = c.rolling(20).std()
            upper = sma20 + 2 * std20
            lower = sma20 - 2 * std20
            p     = current_rate
            bb_range = float(upper.iloc[-1]) - float(lower.iloc[-1])
            if bb_range > 0:
                bb_pos = _safe_float((p - float(lower.iloc[-1])) / bb_range * 100, 1)
        except Exception:
            pass

        daily_ema_alignment = _ema_alignment(c)

        # ── Weekly indicators ─────────────────────────────────────────────────
        weekly_ema_alignment = "insufficient_data"
        weekly_macd = "neutral"
        if not df_w.empty and len(df_w) >= 50:
            cw = df_w["Close"].dropna()
            weekly_ema_alignment = _ema_alignment(cw)
            weekly_macd = _macd_signal(cw)

        # ── momentum_score heuristic ──────────────────────────────────────────
        score = 0.5
        if daily_ema_alignment == "full_bullish":
            score += 0.25
        elif daily_ema_alignment == "full_bearish":
            score -= 0.25
        elif daily_ema_alignment == "bullish":
            score += 0.10
        elif daily_ema_alignment == "bearish":
            score -= 0.10

        if weekly_ema_alignment == "full_bullish":
            score += 0.15
        elif weekly_ema_alignment == "full_bearish":
            score -= 0.15

        if macd == "bullish":
            score += 0.05
        elif macd == "bearish":
            score -= 0.05

        if rsi is not None:
            if 40 <= rsi <= 65:
                score += 0.05
            elif rsi > 75:
                score -= 0.10
            elif rsi < 25:
                score -= 0.10

        score = round(max(0.0, min(1.0, score)), 3)

        market_data = {
            "pair":                  pair,
            "current_rate":          current_rate,
            "daily_ema_alignment":   daily_ema_alignment,
            "weekly_ema_alignment":  weekly_ema_alignment,
            "ema20":                 ema20,
            "ema50":                 ema50,
            "ema200":                ema200,
            "rsi_14":                rsi,
            "macd_signal":           macd,
            "weekly_macd":           weekly_macd,
            "atr_pct":               atr_pct,
            "bb_position_pct":       bb_pos,
            "data_bars":             len(df_d),
        }

        vote = call_claude(
            SYSTEM_PROMPT,
            f"Technical analysis for {pair}: {json.dumps(_clean_nans(market_data))}",
            "fx_technician",
        )
        vote["current_rate"] = current_rate
        vote["atr_pct"]      = atr_pct
        vote["momentum_score"] = vote.get("momentum_score", score)

        _cache[pair] = (vote, time.time())
        return vote

    except Exception as e:
        print(f"[fx_technician] {pair} failed: {e}")
        return {
            "agent":  "fx_technician",
            "pair":   pair,
            "action": "HOLD",
            "confidence": 0.0,
            "rationale":  f"Technical data unavailable: {e}",
            "suggested_position_size_pct": 0,
            "current_rate": None,
            "atr_pct":      None,
            "momentum_score": 0.5,
        }
