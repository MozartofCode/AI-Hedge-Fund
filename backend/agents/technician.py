"""
Technician agent — uses yfinance for OHLCV data and calculates all
technical indicators locally (no AlphaVantage calls needed).
"""
import json
import yfinance as yf
from backend.agents.base_agent import call_claude
from backend.data.indicators import (
    calc_rsi, calc_macd, calc_sma, calc_bbands,
    calc_atr, calc_volume_ratio, calc_adx, calc_roc,
)

SYSTEM_PROMPT = """You are the Technician on an AI trading committee. Analyze technical indicators and price action.
Return ONLY a valid JSON object — no markdown, no explanation, just JSON:
{
  "action": "BUY" | "SELL" | "HOLD",
  "confidence": 0.0-1.0,
  "rationale": "2-3 sentences citing specific indicator values",
  "suggested_position_size_pct": 0-10,
  "momentum_score": 0.0-1.0
}

momentum_score: pure price momentum grade — 1.0 = extremely strong uptrend (ADX>30, RSI 55-70, above all MAs, RS vs SPY strongly positive, ROC positive), 0.0 = strong downtrend (ADX>25 downward, RSI<35, below MAs, RS negative). 0.5 = neutral/choppy.

Signal weights and rules:
- TREND FILTER: Only trade in the direction of the trend. ADX > 25 = trending (signals reliable). ADX < 20 = choppy (reduce confidence significantly, prefer HOLD).
- MOMENTUM: RSI oversold <30 (bullish), overbought >70 (bearish). MACD histogram turning positive = building momentum. ROC_20 > 5% = strong momentum.
- MOVING AVERAGES: Golden Cross (SMA50 > SMA200) = long-term bull. Death Cross = bear. Price above SMA50 = near-term strength.
- RELATIVE STRENGTH: rs_vs_spy_3m > 5% = stock outperforming market (strong signal). < -5% = underperforming (weak signal).
- BREAKOUT: Within 2% of 52w high + volume_ratio > 1.5 = high-probability breakout (bullish). Near 52w low = potential breakdown.
- VOLUME: signal is ONLY meaningful when volume_ratio > 1.2. Low-volume moves should reduce confidence by 30%.
- WEEKLY RSI: If daily RSI signals BUY but weekly RSI > 65, trim confidence (overbought on higher timeframe).
- ATR: High atr_pct_of_price (>3%) = volatile stock, be cautious with confidence.

Prefer SELL with low confidence over HOLD when bearish. Reserve HOLD for genuine neutrality."""


def get_vote(ticker: str) -> dict:
    try:
        hist = yf.Ticker(ticker).history(period="252d")
        if hist.empty or len(hist) < 50:
            raise ValueError(f"Insufficient price history for {ticker}")

        closes  = hist["Close"]
        volumes = hist["Volume"]

        rsi                            = calc_rsi(closes)
        macd, macd_signal, macd_hist   = calc_macd(closes)
        sma50                          = calc_sma(closes, 50)
        sma200                         = calc_sma(closes, 200)
        bb_upper, bb_middle, bb_lower  = calc_bbands(closes)
        atr                            = calc_atr(hist)
        volume_ratio                   = calc_volume_ratio(volumes)
        adx                            = calc_adx(hist)
        roc_20                         = calc_roc(closes, period=20)

        current_price     = round(float(closes.iloc[-1]), 4)
        week52_high       = round(float(hist["High"].max()), 4)
        week52_low        = round(float(hist["Low"].min()), 4)
        pct_from_52w_high = round((current_price - week52_high) / week52_high * 100, 2) if week52_high else None
        pct_from_52w_low  = round((current_price - week52_low)  / week52_low  * 100, 2) if week52_low  else None
        atr_pct           = round(atr / current_price * 100, 2) if atr and current_price else None

        # Weekly RSI — resample daily closes to weekly
        rsi_weekly = None
        try:
            closes_weekly = closes.resample("W-FRI").last().dropna()
            rsi_weekly = calc_rsi(closes_weekly, period=14) if len(closes_weekly) >= 15 else None
        except Exception:
            pass

        # Relative strength vs SPY over 3 months (~63 trading days)
        rs_vs_spy_3m = None
        try:
            spy_closes = yf.Ticker("SPY").history(period="90d")["Close"]
            if len(spy_closes) >= 60 and len(closes) >= 60:
                spy_ret   = (spy_closes.iloc[-1] - spy_closes.iloc[0]) / spy_closes.iloc[0] * 100
                stock_ret = (closes.iloc[-1]      - closes.iloc[-len(spy_closes)]) / closes.iloc[-len(spy_closes)] * 100
                rs_vs_spy_3m = round(float(stock_ret - spy_ret), 2)
        except Exception:
            pass

        # Last 5 bars for price-action context
        recent = hist.tail(5)
        price_action = [
            {"date": str(idx.date()), "close": round(float(row["Close"]), 4), "volume": int(row["Volume"])}
            for idx, row in recent.iterrows()
        ]

        market_data = {
            "ticker":               ticker,
            "current_price":        current_price,
            "rsi_14":               rsi,
            "rsi_weekly":           rsi_weekly,
            "macd":                 macd,
            "macd_signal":          macd_signal,
            "macd_hist":            macd_hist,
            "sma_50":               sma50,
            "sma_200":              sma200,
            "bb_upper":             bb_upper,
            "bb_middle":            bb_middle,
            "bb_lower":             bb_lower,
            "atr_14":               atr,
            "atr_pct_of_price":     atr_pct,
            "volume_ratio_20d":     volume_ratio,
            "adx_14":               adx,
            "roc_20":               roc_20,
            "rs_vs_spy_3m":         rs_vs_spy_3m,
            "week52_high":          week52_high,
            "week52_low":           week52_low,
            "pct_from_52w_high":    pct_from_52w_high,
            "pct_from_52w_low":     pct_from_52w_low,
            "recent_price_action":  price_action,
        }

        return call_claude(
            SYSTEM_PROMPT,
            f"Technical analysis for {ticker}: {json.dumps(market_data)}",
            "technician",
        )
    except Exception as e:
        return {
            "agent": "technician", "ticker": ticker,
            "action": "HOLD", "confidence": 0.0,
            "rationale": f"Data fetch failed: {e}",
            "suggested_position_size_pct": 0,
        }
