"""
Technician agent — uses yfinance for OHLCV data and calculates all
technical indicators locally (no AlphaVantage calls needed).
"""
import json
import yfinance as yf
from backend.agents.base_agent import call_claude
from backend.data.indicators import calc_rsi, calc_macd, calc_sma, calc_bbands, calc_atr, calc_volume_ratio

SYSTEM_PROMPT = """You are the Technician on an AI trading committee. Analyze technical indicators and price action.
Return ONLY a valid JSON object — no markdown, no explanation, just JSON:
{
  "action": "BUY" | "SELL" | "HOLD",
  "confidence": 0.0-1.0,
  "rationale": "2-3 sentences citing specific indicator values",
  "suggested_position_size_pct": 0-10
}
Key signals and weights:
- RSI: overbought >70 (bearish), oversold <30 (bullish)
- MACD: histogram turning positive = bullish momentum; negative = bearish
- Golden Cross (SMA50 > SMA200) = long-term bullish; Death Cross = bearish
- Bollinger Bands: price near lower band = potential reversal/buy; near upper = overbought
- 52-week proximity: within 3% of 52w high + volume spike = breakout signal (bullish); near 52w low = weakness
- Volume ratio: signal is ONLY meaningful when volume_ratio > 1.3 (confirmation). Low-volume moves should reduce confidence.
- ATR: use to gauge volatility — high ATR means wider stops needed, reduce position size confidence accordingly."""


def get_vote(ticker: str) -> dict:
    try:
        # 252 days gives enough history for SMA200 + 52-week high/low
        hist = yf.Ticker(ticker).history(period="252d")
        if hist.empty or len(hist) < 30:
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

        # 52-week high/low and price proximity
        current_price  = round(float(closes.iloc[-1]), 4)
        week52_high    = round(float(hist["High"].max()), 4)
        week52_low     = round(float(hist["Low"].min()), 4)
        pct_from_52w_high = round((current_price - week52_high) / week52_high * 100, 2) if week52_high else None
        pct_from_52w_low  = round((current_price - week52_low)  / week52_low  * 100, 2) if week52_low  else None

        # ATR as % of price (normalised volatility)
        atr_pct = round(atr / current_price * 100, 2) if atr and current_price else None

        # Last 5 bars for price-action context
        recent = hist.tail(5)
        price_action = [
            {
                "date":   str(idx.date()),
                "close":  round(float(row["Close"]), 4),
                "volume": int(row["Volume"]),
            }
            for idx, row in recent.iterrows()
        ]

        market_data = {
            "ticker":               ticker,
            "current_price":        current_price,
            "rsi_14":               rsi,
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
