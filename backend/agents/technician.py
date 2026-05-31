"""
Technician agent — multi-timeframe technical analysis engine.

Daily (2y):   RSI, MACD, SMA 50/200, Stage 2, ATR expansion, Volume Conviction,
              OBV, BB Squeeze, RS vs SPY, Stoch RSI, VWAP, Volume Profile,
              Fibonacci, Order Blocks, Liquidity Sweeps

Weekly (5y):  EMA 20/50/200 alignment, Anchored VWAP, OBV divergence,
              Volume Profile, MACD histogram expansion

Monthly (10y): Market Structure (HH+HL / LL+LH / BOS / CHoCH),
               RSI divergence, MACD signal type
"""
import json
import math
import time
import numpy as np
import pandas as pd
import yfinance as yf
from backend.agents.base_agent import call_claude
from backend.data.indicators import (
    calc_rsi, calc_macd, calc_sma, calc_bbands,
    calc_atr, calc_volume_ratio, calc_adx, calc_roc,
)


def _clean_nans(obj):
    """
    Recursively replace NaN / Inf with None so json.dumps never raises ValueError.
    json.dumps chokes on float('nan') even with default=str — this pre-cleans the tree.
    """
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: _clean_nans(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_nans(v) for v in obj]
    return obj


def _safe_float(val, decimals=2):
    """Convert a value to rounded float, returning None if NaN/None/error."""
    try:
        f = float(val)
        return round(f, decimals) if not (math.isnan(f) or math.isinf(f)) else None
    except Exception:
        return None

_cache: dict = {}
_CACHE_TTL = 600  # 10 minutes


# ══════════════════════════════════════════════════════════════════════════════
#  Pure indicator helpers (ported from multi-timeframe TA engine)
# ══════════════════════════════════════════════════════════════════════════════

def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()

def _rsi_series(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    g = d.clip(lower=0).rolling(n).mean()
    l = (-d.clip(upper=0)).rolling(n).mean()
    return 100 - 100 / (1 + g / (l + 1e-9))

def _stoch_rsi(closes: pd.Series, rsi_n: int = 14, stoch_n: int = 14, k_n: int = 3):
    """Stochastic RSI — more sensitive momentum oscillator than plain RSI.
    Oversold <20, Overbought >80. Faster signals than RSI alone."""
    try:
        r  = _rsi_series(closes, rsi_n)
        lo = r.rolling(stoch_n).min()
        hi = r.rolling(stoch_n).max()
        k  = (r - lo) / (hi - lo + 1e-9) * 100
        val = k.rolling(k_n).mean().iloc[-1]
        d_line = k.rolling(k_n).mean().rolling(3).mean().iloc[-1]
        k_prev = k.rolling(k_n).mean().iloc[-2]
        d_prev = k.rolling(k_n).mean().rolling(3).mean().iloc[-2]
        signal = (
            "oversold"       if not pd.isna(val) and val < 20 else
            "overbought"     if not pd.isna(val) and val > 80 else
            "bullish_cross"  if (not pd.isna(val) and not pd.isna(d_line) and val > d_line and k_prev <= d_prev) else
            "bearish_cross"  if (not pd.isna(val) and not pd.isna(d_line) and val < d_line and k_prev >= d_prev) else
            "neutral"
        )
        return round(float(val), 1) if not pd.isna(val) else None, signal
    except Exception:
        return None, "neutral"


def _market_structure(df: pd.DataFrame, lookback: int = 6) -> dict:
    """
    ICT/SMC market structure detection.
    HH+HL = uptrend, LL+LH = downtrend, BOS = break of structure, CHoCH = trend change.
    """
    try:
        highs = df["High"].iloc[-lookback:].values
        lows  = df["Low"].iloc[-lookback:].values
        hh = all(highs[i] > highs[i-1] for i in range(1, len(highs)))
        hl = all(lows[i]  > lows[i-1]  for i in range(1, len(lows)))
        ll = all(lows[i]  < lows[i-1]  for i in range(1, len(lows)))
        lh = all(highs[i] < highs[i-1] for i in range(1, len(highs)))
        if hh and hl:  return {"trend": "uptrend",       "label": "HH+HL Uptrend (bullish)"}
        if ll and lh:  return {"trend": "downtrend",     "label": "LL+LH Downtrend (bearish)"}
        recent_high = float(df["High"].iloc[-3:-1].max())
        recent_low  = float(df["Low"].iloc[-3:-1].min())
        curr_close  = float(df["Close"].iloc[-1])
        if curr_close > recent_high:
            return {"trend": "bos_bullish",  "label": "BOS Bullish — Break of Structure upward"}
        if curr_close < recent_low:
            return {"trend": "choch_bearish","label": "CHoCH Bearish — Change of Character downward"}
        return {"trend": "ranging", "label": "Ranging / Sideways"}
    except Exception:
        return {"trend": "unknown", "label": "N/A"}


def _rsi_divergence(price_s: pd.Series, rsi_s: pd.Series, lookback: int = 5) -> str:
    """
    Bearish divergence: price makes new high but RSI does not → momentum fading.
    Bullish divergence: price makes new low but RSI does not → sellers exhausted.
    """
    try:
        if len(price_s) < lookback + 2: return "none"
        ph = price_s.iloc[-lookback:]; rh = rsi_s.iloc[-lookback:]
        if price_s.iloc[-1] > ph.iloc[:-1].max() and rsi_s.iloc[-1] < rh.iloc[:-1].max():
            return "bearish_divergence"
        if price_s.iloc[-1] < ph.iloc[:-1].min() and rsi_s.iloc[-1] > rh.iloc[:-1].min():
            return "bullish_divergence"
        return "none"
    except Exception:
        return "none"


def _fibonacci_levels(df: pd.DataFrame, window: int = 120) -> dict:
    """
    Fibonacci retracement/extension from swing high to swing low in last N bars.
    0.382 / 0.5 / 0.618 = major support/resistance levels used by institutions.
    """
    try:
        sub   = df.iloc[-min(window, len(df)):]
        sh    = float(sub["High"].max())
        sl    = float(sub["Low"].min())
        price = float(df["Close"].iloc[-1])
        if sh == sl: return {}
        rng = sh - sl
        levels = {
            "0.0":   round(sh, 2),
            "0.236": round(sh - 0.236 * rng, 2),
            "0.382": round(sh - 0.382 * rng, 2),
            "0.5":   round(sh - 0.5   * rng, 2),
            "0.618": round(sh - 0.618 * rng, 2),
            "0.786": round(sh - 0.786 * rng, 2),
            "1.0":   round(sl, 2),
        }
        nearest = min(levels.items(), key=lambda x: abs(x[1] - price))
        return {
            "levels":        levels,
            "nearest_level": nearest[0],
            "nearest_price": nearest[1],
            "position_pct":  round((price - sl) / rng * 100, 1),
        }
    except Exception:
        return {}


def _volume_profile(df: pd.DataFrame, bins: int = 20) -> dict:
    """
    Volume Profile: POC (most traded price), VAH/VAL (70% value area).
    Price at/above POC = buyers control. Below VAL = in supply zone.
    Price entering value area from below = bullish; from above = bearish.
    """
    try:
        lo = float(df["Low"].min())
        hi = float(df["High"].max())
        if hi == lo: return {}
        edges   = np.linspace(lo, hi, bins + 1)
        centers = (edges[:-1] + edges[1:]) / 2
        vol_at_price = np.zeros(bins)
        closes_arr = df["Close"].values
        vols_arr   = df["Volume"].values
        indices = np.clip(np.searchsorted(edges, closes_arr) - 1, 0, bins - 1)
        for idx, vol in zip(indices, vols_arr):
            vol_at_price[idx] += vol
        poc_idx = int(vol_at_price.argmax())
        poc = round(float(centers[poc_idx]), 2)
        total = vol_at_price.sum(); target = total * 0.70
        va_vol = vol_at_price[poc_idx]; va_lo = poc_idx; va_hi = poc_idx
        while va_vol < target and (va_lo > 0 or va_hi < bins - 1):
            add_lo = vol_at_price[va_lo - 1] if va_lo > 0 else 0
            add_hi = vol_at_price[va_hi + 1] if va_hi < bins - 1 else 0
            if add_lo >= add_hi and va_lo > 0:   va_lo -= 1; va_vol += add_lo
            elif va_hi < bins - 1:               va_hi += 1; va_vol += add_hi
            else: break
        return {
            "poc": poc,
            "vah": round(float(centers[va_hi]), 2),
            "val": round(float(centers[va_lo]), 2),
        }
    except Exception:
        return {}


def _anchored_vwap(df: pd.DataFrame) -> tuple:
    """
    VWAP anchored to 52-week swing low = institutional cost basis from the base.
    Price above AVWAP = longs in profit (bullish). Below = sellers in control.
    """
    try:
        window   = min(252, len(df))
        sub      = df.iloc[-window:]
        anchor_i = int(sub["Low"].values.argmin())
        sub_av   = df.iloc[-(window - anchor_i):]
        typical  = (sub_av["High"] + sub_av["Low"] + sub_av["Close"]) / 3
        vol      = sub_av["Volume"]
        avwap    = float((typical * vol).cumsum().iloc[-1] / vol.cumsum().iloc[-1])
        anchor_date = sub.index[anchor_i]
        date_str = str(anchor_date.date()) if hasattr(anchor_date, "date") else str(anchor_date)[:10]
        return round(avwap, 2), date_str
    except Exception:
        return None, None


def _order_blocks(df: pd.DataFrame, lookback: int = 30) -> dict:
    """
    Order Blocks: High-volume reversal candles = institutional demand/supply zones.
    Bullish OB: Bull candle after a down candle with above-avg volume.
    Bearish OB: Bear candle after an up candle with above-avg volume.
    Active OB = price is currently inside the zone (highest-probability entry).
    """
    try:
        sub = df.iloc[-lookback:]
        price    = float(df["Close"].iloc[-1])
        result   = {"bullish": [], "bearish": []}
        vol_mean = float(sub["Volume"].mean())
        opens  = sub["Open"].values;  closes_arr = sub["Close"].values
        highs  = sub["High"].values;  lows   = sub["Low"].values
        vols   = sub["Volume"].values; dates  = sub.index
        for i in range(1, len(sub)):
            body = abs(closes_arr[i] - opens[i])
            rng  = highs[i] - lows[i]
            if rng < 1e-9: continue
            body_ratio = body / rng
            high_vol   = vols[i] > vol_mean * 1.3
            date_str   = str(dates[i].date()) if hasattr(dates[i], "date") else str(dates[i])[:10]
            # Bullish OB
            if (closes_arr[i-1] < opens[i-1] and closes_arr[i] > opens[i]
                    and body_ratio > 0.5 and high_vol):
                ob_hi = highs[i]; ob_lo = lows[i]
                if ob_lo <= price <= ob_hi * 1.05:
                    result["bullish"].append({"date": date_str, "high": round(ob_hi, 2),
                                              "low": round(ob_lo, 2),
                                              "status": "active" if ob_lo <= price <= ob_hi else "nearby"})
            # Bearish OB
            if (closes_arr[i-1] > opens[i-1] and closes_arr[i] < opens[i]
                    and body_ratio > 0.5 and high_vol):
                ob_hi = highs[i]; ob_lo = lows[i]
                if ob_lo * 0.95 <= price <= ob_hi:
                    result["bearish"].append({"date": date_str, "high": round(ob_hi, 2),
                                              "low": round(ob_lo, 2),
                                              "status": "active" if ob_lo <= price <= ob_hi else "nearby"})
        return result
    except Exception:
        return {"bullish": [], "bearish": []}


def _liquidity_sweeps(df: pd.DataFrame, lookback: int = 20) -> dict:
    """
    Liquidity Sweeps: Wick past swing high/low that closes back inside.
    = smart money grabbed stop orders before reversing.
    Equal Highs/Lows (±0.3% tol): liquidity pools that will be swept next.
    Bullish sweep of swing low = strong buy signal (stops cleared, reversal likely).
    Bearish sweep of swing high = strong sell signal.
    """
    try:
        sub = df.iloc[-lookback:]
        sweeps = []
        highs_arr  = sub["High"].values;   lows_arr   = sub["Low"].values
        closes_arr = sub["Close"].values;  dates       = sub.index
        for i in range(3, len(sub)):
            p_max = float(highs_arr[:i].max()); p_min = float(lows_arr[:i].min())
            date_str = str(dates[i].date()) if hasattr(dates[i], "date") else str(dates[i])[:10]
            if highs_arr[i] > p_max and closes_arr[i] < p_max:
                sweeps.append({"type": "bearish_sweep", "date": date_str,
                               "level": round(p_max, 2), "desc": "Swept swing high — potential reversal down"})
            if lows_arr[i] < p_min and closes_arr[i] > p_min:
                sweeps.append({"type": "bullish_sweep", "date": date_str,
                               "level": round(p_min, 2), "desc": "Swept swing low — potential reversal up"})
        # Equal Highs / Lows
        tol = 0.003
        eq_h = sorted({round(float(h), 2) for i, h in enumerate(highs_arr)
                       if any(i != j and abs(h - highs_arr[j]) / (h + 1e-9) < tol
                              for j in range(len(highs_arr)))}, reverse=True)[:3]
        eq_l = sorted({round(float(l), 2) for i, l in enumerate(lows_arr)
                       if any(i != j and abs(l - lows_arr[j]) / (l + 1e-9) < tol
                              for j in range(len(lows_arr)))})[:3]
        return {
            "recent_sweeps":   sweeps[-5:],
            "equal_highs":     eq_h,
            "equal_lows":      eq_l,
            "liquidity_above": eq_h[0] if eq_h else None,
            "liquidity_below": eq_l[0] if eq_l else None,
        }
    except Exception:
        return {"recent_sweeps": [], "equal_highs": [], "equal_lows": [],
                "liquidity_above": None, "liquidity_below": None}


def _weekly_analysis(df_weekly: pd.DataFrame) -> dict:
    """EMA alignment, Anchored VWAP, OBV divergence, MACD, Volume Profile — weekly bars."""
    out = {}
    try:
        c = df_weekly["Close"]; v = df_weekly["Volume"]
        e20  = _safe_float(_ema(c, 20).iloc[-1])
        e50  = _safe_float(_ema(c, 50).iloc[-1])
        e200 = _safe_float(_ema(c, 200).iloc[-1]) if len(c) >= 200 else None
        if e20  is not None: out["weekly_ema20"] = e20
        if e50  is not None: out["weekly_ema50"] = e50
        if e200 is not None: out["weekly_ema200"] = e200
        out["weekly_ema_alignment"] = (
            "full_bullish"  if e200 and e20 and e50 and e20 > e50 > e200 else
            "full_bearish"  if e200 and e20 and e50 and e20 < e50 < e200 else "mixed"
        )
        # OBV divergence
        obv_s = (np.sign(c.diff()) * v).fillna(0).cumsum()
        if len(c) >= 10:
            cp = c.iloc[-8:]; op = obv_s.iloc[-8:]
            if c.iloc[-1] > cp.iloc[:-1].max() and obv_s.iloc[-1] < op.iloc[:-1].max():
                out["weekly_obv_divergence"] = "bearish_divergence"
            elif c.iloc[-1] < cp.iloc[:-1].min() and obv_s.iloc[-1] > op.iloc[:-1].min():
                out["weekly_obv_divergence"] = "bullish_divergence"
            else:
                out["weekly_obv_divergence"] = "confirming"
        # MACD histogram expanding?
        ml = _ema(c, 12) - _ema(c, 26); sig = _ema(ml, 9); hist = ml - sig
        mh0 = _safe_float(hist.iloc[-1], 4); mh1 = _safe_float(hist.iloc[-2], 4)
        if mh0 is not None: out["weekly_macd_hist"] = mh0
        if mh0 is not None and mh1 is not None:
            out["weekly_macd_expanding"] = abs(mh0) > abs(mh1)
        # Anchored VWAP
        avwap, anchor_date = _anchored_vwap(df_weekly)
        if avwap:
            out["weekly_avwap"]        = avwap
            out["weekly_avwap_anchor"] = anchor_date
            out["weekly_price_vs_avwap"] = round((float(c.iloc[-1]) / avwap - 1) * 100, 2)
        # Volume Profile (weekly) — must use .iloc for DatetimeIndex
        vp = _volume_profile(df_weekly.iloc[-52:] if len(df_weekly) >= 52 else df_weekly)
        if vp: out["weekly_volume_profile"] = vp
    except Exception as exc:
        print(f"[technician] weekly_analysis error: {exc}")
    return out


def _monthly_analysis(df_monthly: pd.DataFrame) -> dict:
    """Market structure, RSI divergence, MACD signal type — monthly bars."""
    out = {}
    try:
        c = df_monthly["Close"]
        # Market structure on monthly
        out["monthly_market_structure"] = _market_structure(df_monthly, lookback=6)
        # RSI divergence on monthly
        r_mo = _rsi_series(c)
        out["monthly_rsi_divergence"] = _rsi_divergence(c, r_mo, lookback=5)
        # MACD histogram signal
        ml = _ema(c, 12) - _ema(c, 26); sig = _ema(ml, 9); hist = ml - sig
        out["monthly_macd_signal"] = (
            "golden_cross" if hist.iloc[-1] > 0 and hist.iloc[-2] <= 0 else
            "death_cross"  if hist.iloc[-1] < 0 and hist.iloc[-2] >= 0 else
            "bullish"      if hist.iloc[-1] > 0 else "bearish"
        )
        # EMA 20 vs SMA 50 alignment on monthly
        e20_mo = _safe_float(_ema(c, 20).iloc[-1])
        s50_mo = _safe_float(c.rolling(50).mean().iloc[-1])
        if e20_mo is not None: out["monthly_ema20"] = e20_mo
        if s50_mo is not None: out["monthly_sma50"] = s50_mo
        if e20_mo is not None and s50_mo is not None:
            out["monthly_trend_bias"] = "bullish" if e20_mo > s50_mo else "bearish"
    except Exception as exc:
        print(f"[technician] monthly_analysis error: {exc}")
    return out


# ══════════════════════════════════════════════════════════════════════════════
#  System prompt
# ══════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are the Technician on an AI investment committee hunting for 10X opportunities.
Return ONLY a valid JSON object — no markdown, no explanation, just JSON:
{
  "action": "BUY" | "SELL" | "HOLD",
  "confidence": 0.0-1.0,
  "rationale": "1 plain-English sentence an everyday investor would understand — no jargon like 'order blocks', 'VWAP', 'RSI', 'liquidity sweep', 'BOS'. Say what the chart is actually doing (e.g. 'The stock is in a clear uptrend and just bounced off support, suggesting buyers are still in control.' or 'The stock is breaking down below its 200-day average on rising volume — momentum is clearly bearish.').",
  "suggested_position_size_pct": 0-12,
  "momentum_score": 0.0-1.0
}

momentum_score: pure momentum grade — 1.0=Stage 2 uptrend, ADX>25, full_bullish EMA alignment, RS outperforming. 0.0=strong downtrend. 0.5=neutral.

═══ PRIORITY SIGNALS (weight heavily) ═══

1. STAGE 2 UPTREND: stage2_uptrend=True → price > 200d MA AND 200d MA rising. ALL 10X moves happen here. BUY with high confidence. Stage 2 ending (200d MA flattening) = reduce.

2. WEEKLY EMA ALIGNMENT (weekly_ema_alignment):
   - full_bullish (20>50>200 weekly) = sustained institutional uptrend. Highest-quality trend.
   - full_bearish = avoid longs.
   - mixed = wait for clarity.

3. MONTHLY MARKET STRUCTURE (monthly_market_structure.trend):
   - uptrend (HH+HL) = only look for long setups
   - downtrend (LL+LH) = only look for short/avoid setups
   - bos_bullish = Break of Structure upward — potential new uptrend starting (BUY signal)
   - choch_bearish = Change of Character — trend may be reversing (reduce/SELL signal)

4. ORDER BLOCKS (order_blocks.bullish / bearish):
   Active = price is inside the institutional demand/supply zone. Highest-probability entry.
   Nearby = price approaching the zone. Prepare for entry.
   Bullish OB = institutional demand zone. Price at active bullish OB = strong BUY.
   Bearish OB = institutional supply zone. Price at active bearish OB = strong SELL.

5. LIQUIDITY SWEEPS (liquidity_sweeps):
   bullish_sweep (swept swing low, closed above) = stop hunt complete, reversal likely UP. High-conviction BUY.
   bearish_sweep (swept swing high, closed below) = stop hunt complete, reversal likely DOWN. High-conviction SELL.
   equal_highs = liquidity pool above. Price likely to sweep it before reversing.
   equal_lows = liquidity pool below. Price likely to sweep it before reversing.

6. ANCHORED VWAP (weekly_avwap / weekly_price_vs_avwap):
   Above AVWAP = longs profitable since the base. Bullish.
   Below AVWAP = sellers dominant since the base. Bearish.
   Reclaim of AVWAP from below = strong BUY (institutions re-entering).

7. VOLUME PROFILE (volume_profile / weekly_volume_profile):
   POC = magnetic price level — expect price to hover or react here.
   Above VAH = price accepted above value (bullish). Below VAL = below value (bearish).
   Entering value area from below = bullish. From above = bearish.

8. FIBONACCI (fibonacci):
   0.382 / 0.5 / 0.618 = high-probability support in uptrend. At these levels + bullish sweep = BUY.
   0.236 rejection = trend strong. 0.786 hold = last chance for bulls.

9. ATR EXPANSION (atr_expansion_ratio > 1.3): Volatility expanding = early growth phase. Combine with bullish structure = explosive move coming.

10. VOLUME CONVICTION (vol_conviction_ratio > 2.0): Institutions buying on strength. > 1.5 = accumulation. < 0.8 = distribution.

11. STOCH RSI (stoch_rsi / stoch_rsi_signal):
    oversold (<20) in uptrend = buy dip. overbought (>80) = take profit / tighten stop.
    bullish_cross in oversold = high-probability entry. Bearish cross in overbought = exit.

12. MONTHLY RSI DIVERGENCE (monthly_rsi_divergence):
    bullish_divergence on monthly = multi-month bottom forming. Very high confidence BUY on pullback.
    bearish_divergence on monthly = multi-month top forming. Reduce position / SELL.

13. WEEKLY OBV DIVERGENCE (weekly_obv_divergence):
    bullish_divergence = smart money accumulating while price falls. Stealth accumulation = BUY.
    bearish_divergence = distribution. Reduce.

Standard signals (still important):
- ADX > 25 = trending (signals reliable). ADX < 20 = choppy (reduce confidence 40%).
- RSI 50-70 in uptrend = healthy momentum. MACD hist positive and expanding = BUY.
- BB squeeze (bb_squeeze=True) + Stage 2 + bullish OB = explosive breakout setup.
- RS vs SPY +10%: leadership stock (10X candidates always lead the market).
- Near 52w high (<-3%) + vol_ratio > 1.5 = high-probability breakout.

Synthesis rule: Score higher when multiple timeframes agree (monthly uptrend + weekly full_bullish + daily bullish OB + bullish sweep = 4-star setup). Conflicting timeframes = HOLD or reduce confidence."""


# ══════════════════════════════════════════════════════════════════════════════
#  Main agent function
# ══════════════════════════════════════════════════════════════════════════════

def get_vote(ticker: str) -> dict:
    cached = _cache.get(ticker)
    if cached and time.time() - cached["ts"] < _CACHE_TTL:
        return cached["data"]

    try:
        t = yf.Ticker(ticker)

        # ── Fetch all three timeframes ────────────────────────────────────────
        hist         = t.history(period="2y",  interval="1d")   # daily  ~500 bars
        hist_weekly  = t.history(period="5y",  interval="1wk")  # weekly ~260 bars
        hist_monthly = t.history(period="10y", interval="1mo")  # monthly ~120 bars

        if hist.empty or len(hist) < 50:
            raise ValueError(f"Insufficient daily price history for {ticker}")

        closes  = hist["Close"]
        volumes = hist["Volume"]
        high    = hist["High"]
        low     = hist["Low"]

        # ── Existing daily indicators (unchanged) ─────────────────────────────
        rsi_val                        = calc_rsi(closes)
        macd_val, macd_signal, macd_hist = calc_macd(closes)
        sma50                          = calc_sma(closes, 50)
        sma200                         = calc_sma(closes, 200)
        bb_upper, bb_middle, bb_lower  = calc_bbands(closes)
        atr_val                        = calc_atr(hist)
        volume_ratio                   = calc_volume_ratio(volumes)
        adx_val                        = calc_adx(hist)
        roc_20                         = calc_roc(closes, period=20)

        current_price     = round(float(closes.iloc[-1]), 4)
        week52_high       = round(float(high.max()), 4)
        week52_low        = round(float(low.min()), 4)
        pct_from_52w_high = round((current_price - week52_high) / week52_high * 100, 2) if week52_high else None
        pct_from_52w_low  = round((current_price - week52_low)  / week52_low  * 100, 2) if week52_low  else None
        atr_pct           = round(atr_val / current_price * 100, 2) if atr_val and current_price else None

        # Weekly RSI
        rsi_weekly = None
        try:
            closes_weekly = closes.resample("W-FRI").last().dropna()
            rsi_weekly = calc_rsi(closes_weekly, period=14) if len(closes_weekly) >= 15 else None
        except Exception:
            pass

        # SMA200 slope
        sma200_slope_pct = None
        try:
            if len(closes) >= 221 and sma200:
                sma200_21d_ago = float(closes.iloc[-221:-21].mean())
                if sma200_21d_ago > 0:
                    sma200_slope_pct = round((sma200 - sma200_21d_ago) / sma200_21d_ago * 100, 3)
        except Exception:
            pass

        # Stage 2 uptrend
        stage2_uptrend = bool(
            sma200 is not None and current_price > sma200
            and sma200_slope_pct is not None and sma200_slope_pct > 0
        )

        # ATR expansion ratio
        atr_expansion_ratio = None
        try:
            tr = pd.concat([
                high - low,
                (high - closes.shift()).abs(),
                (low  - closes.shift()).abs(),
            ], axis=1).max(axis=1)
            atr_rolling = tr.rolling(14).mean().dropna()
            if len(atr_rolling) >= 51:
                atr_50d_avg = float(atr_rolling.iloc[-51:-1].mean())
                atr_current = float(atr_rolling.iloc[-1])
                if atr_50d_avg > 0:
                    atr_expansion_ratio = round(atr_current / atr_50d_avg, 2)
        except Exception:
            pass

        # Volume conviction
        vol_conviction_ratio = None
        try:
            last20 = hist.tail(21)
            price_change = last20["Close"].diff().dropna()
            up_vol   = last20["Volume"].iloc[1:][price_change > 0]
            down_vol = last20["Volume"].iloc[1:][price_change < 0]
            if not up_vol.empty and not down_vol.empty:
                vol_conviction_ratio = round(float(up_vol.mean() / down_vol.mean()), 2)
        except Exception:
            pass

        # Volume trend
        vol_trend_pct = None
        try:
            if len(volumes) >= 150:
                avg_50  = float(volumes.iloc[-50:].mean())
                avg_150 = float(volumes.iloc[-150:].mean())
                if avg_150 > 0:
                    vol_trend_pct = round((avg_50 - avg_150) / avg_150 * 100, 1)
        except Exception:
            pass

        # RS vs SPY
        rs_vs_spy_3m = None
        try:
            spy_closes = yf.Ticker("SPY").history(period="90d")["Close"]
            if len(spy_closes) >= 60 and len(closes) >= 60:
                spy_ret   = (spy_closes.iloc[-1] - spy_closes.iloc[0]) / spy_closes.iloc[0] * 100
                stock_ret = (closes.iloc[-1] - closes.iloc[-len(spy_closes)]) / closes.iloc[-len(spy_closes)] * 100
                rs_vs_spy_3m = round(float(stock_ret - spy_ret), 2)
        except Exception:
            pass

        # OBV trend
        obv_trend_pct = None
        try:
            direction = closes.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
            obv = (volumes * direction).cumsum()
            if len(obv) >= 50:
                obv_sma20 = float(obv.iloc[-20:].mean())
                obv_sma50 = float(obv.iloc[-50:].mean())
                if abs(obv_sma50) > 0:
                    obv_trend_pct = round((obv_sma20 - obv_sma50) / abs(obv_sma50) * 100, 2)
        except Exception:
            pass

        # BB squeeze
        bb_squeeze = False; bb_squeeze_pctile = None; bb_width_pct = None
        try:
            roll_std  = closes.rolling(20).std()
            roll_mid  = closes.rolling(20).mean()
            bb_widths = (roll_std * 4 / roll_mid * 100).dropna()
            if len(bb_widths) >= 20:
                bb_width_pct = round(float(bb_widths.iloc[-1]), 2)
                if len(bb_widths) >= 52:
                    pctile = float((bb_widths < bb_widths.iloc[-1]).mean() * 100)
                    bb_squeeze_pctile = round(pctile, 1)
                    bb_squeeze = pctile < 20
        except Exception:
            pass

        # ── NEW: Stoch RSI ────────────────────────────────────────────────────
        stoch_rsi_k, stoch_rsi_signal = _stoch_rsi(closes)

        # ── NEW: Daily VWAP ───────────────────────────────────────────────────
        vwap_daily = None
        try:
            typical = (high + low + closes) / 3
            vwap_daily = round(float((typical * volumes).cumsum().iloc[-1] / volumes.cumsum().iloc[-1]), 2)
        except Exception:
            pass

        # ── NEW: Volume Profile (daily, last 60 bars) ─────────────────────────
        vp_daily = _volume_profile(hist.tail(60) if len(hist) >= 60 else hist)

        # ── NEW: Fibonacci (daily, last 120 bars) ────────────────────────────
        fib_data = _fibonacci_levels(hist, window=120)

        # ── NEW: Market Structure (daily, last 6 bars) ────────────────────────
        ms_daily = _market_structure(hist, lookback=6)

        # ── NEW: Order Blocks (daily, last 30 bars) ───────────────────────────
        ob_data = _order_blocks(hist, lookback=30)

        # ── NEW: Liquidity Sweeps (daily, last 20 bars) ───────────────────────
        lq_data = _liquidity_sweeps(hist, lookback=20)

        # ── NEW: Weekly multi-indicator analysis ──────────────────────────────
        weekly_data = {}
        if not hist_weekly.empty and len(hist_weekly) >= 20:
            weekly_data = _weekly_analysis(hist_weekly)

        # ── NEW: Monthly analysis ─────────────────────────────────────────────
        monthly_data = {}
        if not hist_monthly.empty and len(hist_monthly) >= 10:
            monthly_data = _monthly_analysis(hist_monthly)

        # ── Recent price action ───────────────────────────────────────────────
        price_action = [
            {"date": str(idx.date()), "close": round(float(row["Close"]), 4), "volume": int(row["Volume"])}
            for idx, row in hist.tail(5).iterrows()
        ]

        # ── Assemble market_data ──────────────────────────────────────────────
        market_data = {
            "ticker":               ticker,
            "current_price":        current_price,
            # Core momentum (daily)
            "rsi_14":               rsi_val,
            "rsi_weekly":           rsi_weekly,
            "macd":                 macd_val,
            "macd_signal":          macd_signal,
            "macd_hist":            macd_hist,
            "adx_14":               adx_val,
            "roc_20":               roc_20,
            # Moving averages
            "sma_50":               sma50,
            "sma_200":              sma200,
            "sma200_slope_pct":     sma200_slope_pct,
            # ★ Stage 2 / institutional signals
            "stage2_uptrend":       stage2_uptrend,
            "atr_expansion_ratio":  atr_expansion_ratio,
            "vol_conviction_ratio": vol_conviction_ratio,
            "vol_trend_pct":        vol_trend_pct,
            "rs_vs_spy_3m":         rs_vs_spy_3m,
            # Bands & volatility
            "bb_upper":             bb_upper,
            "bb_middle":            bb_middle,
            "bb_lower":             bb_lower,
            "atr_14":               atr_val,
            "atr_pct_of_price":     atr_pct,
            # Volume
            "volume_ratio_20d":     volume_ratio,
            "obv_trend_pct":        obv_trend_pct,
            # BB squeeze
            "bb_squeeze":           bb_squeeze,
            "bb_squeeze_pctile":    bb_squeeze_pctile,
            "bb_width_pct":         bb_width_pct,
            # 52-week range
            "week52_high":          week52_high,
            "week52_low":           week52_low,
            "pct_from_52w_high":    pct_from_52w_high,
            "pct_from_52w_low":     pct_from_52w_low,
            "recent_price_action":  price_action,
            # ★ NEW: Stoch RSI
            "stoch_rsi":            stoch_rsi_k,
            "stoch_rsi_signal":     stoch_rsi_signal,
            # ★ NEW: VWAP
            "vwap_daily":           vwap_daily,
            # ★ NEW: Volume Profile (daily)
            "volume_profile":       vp_daily,
            # ★ NEW: Fibonacci
            "fibonacci":            fib_data,
            # ★ NEW: Market Structure (daily)
            "daily_market_structure": ms_daily,
            # ★ NEW: Order Blocks
            "order_blocks":         ob_data,
            # ★ NEW: Liquidity Sweeps
            "liquidity_sweeps":     lq_data,
            # ★ NEW: Weekly analysis
            **weekly_data,
            # ★ NEW: Monthly analysis
            **monthly_data,
        }

        vote = call_claude(
            SYSTEM_PROMPT,
            f"Technical analysis for {ticker}: {json.dumps(_clean_nans(market_data))}",
            "technician",
        )
        vote["current_price"] = current_price
        vote["atr_pct"]       = atr_pct
        _cache[ticker] = {"ts": time.time(), "data": vote}
        return vote

    except Exception as e:
        import traceback
        print(f"[technician] {ticker} FAILED: {e}\n{traceback.format_exc()}")
        return {
            "agent": "technician", "ticker": ticker,
            "action": "HOLD", "confidence": 0.0,
            "rationale": f"Data fetch failed: {e}",
            "suggested_position_size_pct": 0,
            "current_price": None,
        }
