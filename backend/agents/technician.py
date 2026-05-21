"""
Technician agent — uses yfinance for OHLCV data and calculates all
technical indicators locally (no AlphaVantage calls needed).
"""
import json
import yfinance as yf
from backend.agents.base_agent import call_claude
from backend.data.indicators import calc_rsi, calc_macd, calc_sma, calc_bbands

SYSTEM_PROMPT = """You are the Technician on an AI trading committee. Analyze technical indicators and price action.
Return ONLY a valid JSON object — no markdown, no explanation, just JSON:
{
  "action": "BUY" | "SELL" | "HOLD",
  "confidence": 0.0-1.0,
  "rationale": "2-3 sentences citing specific indicator values",
  "suggested_position_size_pct": 0-10
}
Weight these signals: RSI overbought >70 / oversold <30, MACD crossovers, Golden Cross (SMA50 > SMA200) / Death Cross, Bollinger Band squeezes, volume spikes."""


def get_vote(ticker: str) -> dict:
    try:
        # 250 days gives enough history for SMA200 + all other indicators
        hist = yf.Ticker(ticker).history(period="250d")
        if hist.empty or len(hist) < 30:
            raise ValueError(f"Insufficient price history for {ticker}")

        closes  = hist["Close"]
        volumes = hist["Volume"]

        rsi                         = calc_rsi(closes)
        macd, macd_signal, macd_hist = calc_macd(closes)
        sma50                       = calc_sma(closes, 50)
        sma200                      = calc_sma(closes, 200)
        bb_upper, bb_middle, bb_lower = calc_bbands(closes)

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
            "ticker":             ticker,
            "rsi_14":             rsi,
            "macd":               macd,
            "macd_signal":        macd_signal,
            "macd_hist":          macd_hist,
            "sma_50":             sma50,
            "sma_200":            sma200,
            "bb_upper":           bb_upper,
            "bb_middle":          bb_middle,
            "bb_lower":           bb_lower,
            "recent_price_action": price_action,
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
