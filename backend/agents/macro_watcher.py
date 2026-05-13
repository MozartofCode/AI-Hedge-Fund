import json
from backend.agents.base_agent import call_claude
from backend.data.alphavantage_client import get_sector_performance, get_global_quote
from backend.data.finnhub_client import get_economic_calendar

SYSTEM_PROMPT = """You are the Macro Watcher on an AI trading committee. Analyze macro conditions, sector rotation, and market-wide risk.
Return ONLY a valid JSON object — no markdown, no explanation, just JSON:
{
  "action": "BUY" | "SELL" | "HOLD",
  "confidence": 0.0-1.0,
  "rationale": "2-3 sentences citing macro conditions",
  "suggested_position_size_pct": 0-10,
  "risk_off": false
}
Set "risk_off": true if VIX > 25 OR a high-impact macro event (Fed meeting, CPI) is within 2 days.
Key signals: VIX level, sector ETF momentum (XLK/XLE/XLF/XLV), upcoming Fed/CPI dates, USD strength, yield curve shape."""


def get_vote(ticker: str) -> dict:
    try:
        sector_perf = get_sector_performance()
        vix_quote = get_global_quote("VIX")
        econ_calendar = get_economic_calendar()

        vix_price = vix_quote.get("05. price")

        # 1-day sector performance snapshot
        sector_1d = sector_perf.get("Rank B: 1 Day Performance", {})

        # Upcoming high-impact US events (next 14 days)
        events = []
        if isinstance(econ_calendar, dict) and econ_calendar.get("economicCalendar"):
            events = [
                {
                    "event": e.get("event"),
                    "date": e.get("time"),
                    "impact": e.get("impact"),
                    "country": e.get("country"),
                }
                for e in econ_calendar["economicCalendar"]
                if e.get("impact") in ("high", "medium") and e.get("country") == "US"
            ][:8]

        market_data = {
            "ticker": ticker,
            "vix": vix_price,
            "sector_1d_performance": sector_1d,
            "upcoming_us_events": events,
        }

        return call_claude(
            SYSTEM_PROMPT,
            f"Macro analysis for {ticker}: {json.dumps(market_data)}",
            "macro_watcher",
        )
    except Exception as e:
        return {
            "agent": "macro_watcher", "ticker": ticker,
            "action": "HOLD", "confidence": 0.0,
            "rationale": f"Data fetch failed: {e}",
            "suggested_position_size_pct": 0,
            "risk_off": False,
        }
