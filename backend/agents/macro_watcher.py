"""
Macro Watcher agent — uses yfinance for VIX, yield curve, USD index,
and sector ETF performance (no AlphaVantage calls). Economic calendar
from Finnhub. Results are cached for 30 min so the data is fetched only
once per committee session regardless of how many tickers are in the watchlist.
"""
import json
import time
import yfinance as yf
from backend.agents.base_agent import call_claude
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
Set "risk_off": true if VIX > 25 OR yield curve is inverted (spread_10y_3m < 0) OR a high-impact macro event (Fed meeting, CPI) is within 2 days.
Key signals:
- VIX: <15 = calm/bullish, 15-25 = neutral, >25 = fear/risk-off, >35 = panic/avoid
- Yield curve spread (10Y - 3M): positive = normal/healthy; negative = inverted = recession signal (bearish)
- USD 1-week change: USD strengthening >1% = headwind for equities/commodities; weakening = tailwind
- Sector 1d performance: identify rotation (e.g. money moving from tech to utilities = defensive positioning)
- Upcoming high-impact US events: Fed/CPI/jobs data within 2 days = increase caution"""

# Sector ETFs tracked for 1-day performance
_SECTOR_ETFS = {
    "Technology":       "XLK",
    "Healthcare":       "XLV",
    "Energy":           "XLE",
    "Financials":       "XLF",
    "Consumer Disc":    "XLY",
    "Consumer Staples": "XLP",
    "Industrials":      "XLI",
    "Utilities":        "XLU",
    "Materials":        "XLB",
    "Real Estate":      "XLRE",
}

# In-memory cache shared across all tickers in one committee session
_cache: dict = {"data": None, "ts": 0.0}
_CACHE_TTL = 1800  # 30 minutes


def _get_macro_snapshot() -> dict:
    """Fetch VIX, yield curve, USD, sector performance + econ calendar. Cached 30 min."""
    global _cache
    if time.time() - _cache["ts"] < _CACHE_TTL and _cache["data"] is not None:
        return _cache["data"]

    # ── VIX ───────────────────────────────────────────────────────────────────
    vix = None
    try:
        vix_hist = yf.Ticker("^VIX").history(period="2d")
        if not vix_hist.empty:
            vix = round(float(vix_hist["Close"].iloc[-1]), 2)
    except Exception:
        pass

    # ── Yield curve: 10-year minus 3-month (classic recession indicator) ──────
    yield_spread_10y_3m = None
    try:
        t3m  = yf.Ticker("^IRX").history(period="2d")["Close"]  # 13-week T-bill (proxy for 3M)
        t10y = yf.Ticker("^TNX").history(period="2d")["Close"]  # 10-year yield
        if not t3m.empty and not t10y.empty:
            yield_spread_10y_3m = round(float(t10y.iloc[-1]) - float(t3m.iloc[-1]), 3)
    except Exception:
        pass

    # ── USD index 1-week change ───────────────────────────────────────────────
    usd_1w_change_pct = None
    try:
        dxy = yf.Ticker("DX-Y.NYB").history(period="10d")["Close"].dropna()
        if len(dxy) >= 5:
            usd_1w_change_pct = round(
                float((dxy.iloc[-1] - dxy.iloc[-5]) / dxy.iloc[-5] * 100), 2
            )
    except Exception:
        pass

    # ── Sector 1-day returns ──────────────────────────────────────────────────
    sector_1d = {}
    try:
        etf_list = list(_SECTOR_ETFS.values())
        hist = yf.download(etf_list, period="5d", progress=False, auto_adjust=True)["Close"]
        for sector, etf in _SECTOR_ETFS.items():
            try:
                series = hist[etf].dropna()
                if len(series) >= 2:
                    pct = (series.iloc[-1] - series.iloc[-2]) / series.iloc[-2] * 100
                    sector_1d[sector] = round(float(pct), 2)
            except Exception:
                pass
    except Exception:
        pass

    # ── Economic calendar (Finnhub — cached here so not called 10× per session) ──
    events = []
    try:
        cal = get_economic_calendar()
        if isinstance(cal, dict) and cal.get("economicCalendar"):
            events = [
                {
                    "event":  e.get("event"),
                    "date":   e.get("time"),
                    "impact": e.get("impact"),
                }
                for e in cal["economicCalendar"]
                if e.get("impact") in ("high", "medium") and e.get("country") == "US"
            ][:8]
    except Exception:
        pass

    data = {
        "vix":                    vix,
        "yield_spread_10y_3m":    yield_spread_10y_3m,
        "yield_curve_inverted":   (yield_spread_10y_3m < 0) if yield_spread_10y_3m is not None else None,
        "usd_1w_change_pct":      usd_1w_change_pct,
        "sector_1d_performance":  sector_1d,
        "upcoming_us_events":     events,
    }
    _cache = {"data": data, "ts": time.time()}
    return data


def get_vote(ticker: str) -> dict:
    try:
        macro = _get_macro_snapshot()

        market_data = {
            "ticker":                  ticker,
            "vix":                     macro["vix"],
            "yield_spread_10y_3m":     macro["yield_spread_10y_3m"],
            "yield_curve_inverted":    macro["yield_curve_inverted"],
            "usd_1w_change_pct":       macro["usd_1w_change_pct"],
            "sector_1d_performance":   macro["sector_1d_performance"],
            "upcoming_us_events":      macro["upcoming_us_events"],
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
