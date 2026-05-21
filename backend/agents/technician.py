import json
from backend.agents.base_agent import call_claude
from backend.data.alphavantage_client import get_rsi, get_macd, get_sma, get_bbands
from backend.broker.paper_broker import get_historical_bars

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
        rsi = get_rsi(ticker)
        macd = get_macd(ticker)
        sma50 = get_sma(ticker, 50)
        sma200 = get_sma(ticker, 200)
        bbands = get_bbands(ticker)
        bars = get_historical_bars(ticker, days=30)

        recent = bars[-5:] if len(bars) >= 5 else bars
        price_action = [
            {"date": str(b.get("timestamp", "")), "close": b.get("close"), "volume": b.get("volume")}
            for b in recent
        ]

        market_data = {
            "ticker": ticker,
            "rsi_14": rsi.get("RSI"),
            "macd": macd.get("MACD"),
            "macd_signal": macd.get("MACD_Signal"),
            "macd_hist": macd.get("MACD_Hist"),
            "sma_50": sma50.get("SMA"),
            "sma_200": sma200.get("SMA"),
            "bb_upper": bbands.get("Real Upper Band"),
            "bb_middle": bbands.get("Real Middle Band"),
            "bb_lower": bbands.get("Real Lower Band"),
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
