"""
Macro Watcher agent — VIX, yield curve, USD, SPY trend, sector momentum.
Cached 30 min so macro data is fetched once per session for all 15 tickers.
Also injects raw spy_above_200d and vix_raw into the vote dict so the
orchestrator can use them for dynamic agent weight selection.
"""
import json
import time
import yfinance as yf
from backend.agents.base_agent import call_claude
from backend.data.indicators import calc_sma
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

Set "risk_off": true if ANY of: VIX > 25, yield curve inverted (spread < 0), SPY below 200-day MA, OR high-impact event within 2 days.

Key signals:
- MARKET REGIME (most important): SPY above both 50d and 200d MA = confirmed bull market (favor BUY). SPY below 200d MA = bear market (favor SELL/HOLD).
- VIX: <15 = calm/bullish, 15-25 = neutral, >25 = risk-off, >35 = panic (SELL everything)
- Yield curve (10Y - 3M): positive = healthy. Inverted (< 0) = recession risk (risk_off = true, bearish)
- USD strength: 1w change > +1% = headwind for equities; weakening = tailwind
- SECTOR MOMENTUM: Use 20d trends, not just 1d blips. Money rotating INTO ticker's sector over 20d = tailwind. OUT = headwind.
- Upcoming high-impact events (Fed, CPI, NFP) within 2 days = increase caution, risk_off = true

Prefer SELL with low confidence over HOLD when bearish. Reserve HOLD for genuine neutrality."""

_SECTOR_ETFS = {
    "Technology":          "XLK",
    "Healthcare":          "XLV",
    "Energy":              "XLE",
    "Financials":          "XLF",
    "Consumer Disc":       "XLY",
    "Consumer Staples":    "XLP",
    "Industrials":         "XLI",
    "Utilities":           "XLU",
    "Materials":           "XLB",
    "Real Estate":         "XLRE",
}

# Ticker → sector for watchlist
_TICKER_SECTOR = {
    "AAPL": "Technology", "NVDA": "Technology", "MSFT": "Technology",
    "GOOGL": "Technology", "META": "Technology", "AMD": "Technology",
    "AMZN": "Consumer Disc", "TSLA": "Consumer Disc",
    "JPM": "Financials", "GS": "Financials",
    "UNH": "Healthcare", "LLY": "Healthcare",
    "XOM": "Energy",
    "SPY": "Broad Market", "QQQ": "Technology",
}

_cache: dict = {"data": None, "ts": 0.0}
_CACHE_TTL   = 1800  # 30 minutes


def _get_macro_snapshot() -> dict:
    global _cache
    if time.time() - _cache["ts"] < _CACHE_TTL and _cache["data"] is not None:
        return _cache["data"]

    # ── VIX ───────────────────────────────────────────────────────────────────
    vix = None
    try:
        vix_hist = yf.Ticker("^VIX").history(period="5d")
        if not vix_hist.empty:
            vix = round(float(vix_hist["Close"].iloc[-1]), 2)
    except Exception:
        pass

    # ── SPY trend — bull/bear market regime ───────────────────────────────────
    spy_above_50d  = None
    spy_above_200d = None
    spy_roc_20d    = None
    try:
        spy_closes = yf.Ticker("SPY").history(period="252d")["Close"].dropna()
        if len(spy_closes) >= 200:
            sma50  = calc_sma(spy_closes, 50)
            sma200 = calc_sma(spy_closes, 200)
            price  = float(spy_closes.iloc[-1])
            spy_above_50d  = bool(price > sma50)  if sma50  else None
            spy_above_200d = bool(price > sma200) if sma200 else None
        if len(spy_closes) >= 21:
            spy_roc_20d = round(float(
                (spy_closes.iloc[-1] - spy_closes.iloc[-21]) / spy_closes.iloc[-21] * 100
            ), 2)
    except Exception:
        pass

    # ── Yield curve: 10-year minus 3-month ────────────────────────────────────
    yield_spread_10y_3m = None
    try:
        t3m  = yf.Ticker("^IRX").history(period="5d")["Close"].dropna()
        t10y = yf.Ticker("^TNX").history(period="5d")["Close"].dropna()
        if not t3m.empty and not t10y.empty:
            yield_spread_10y_3m = round(float(t10y.iloc[-1]) - float(t3m.iloc[-1]), 3)
    except Exception:
        pass

    # ── USD index 1-week change ───────────────────────────────────────────────
    usd_1w_change_pct = None
    try:
        dxy = yf.Ticker("DX-Y.NYB").history(period="10d")["Close"].dropna()
        if len(dxy) >= 5:
            usd_1w_change_pct = round(float((dxy.iloc[-1] - dxy.iloc[-5]) / dxy.iloc[-5] * 100), 2)
    except Exception:
        pass

    # ── Sector performance: 1d, 5d, 20d ─────────────────────────────────────
    sector_perf = {}
    try:
        etf_list = list(_SECTOR_ETFS.values())
        hist = yf.download(etf_list, period="30d", progress=False, auto_adjust=True)["Close"]
        for sector, etf in _SECTOR_ETFS.items():
            try:
                s = hist[etf].dropna()
                perf = {}
                if len(s) >= 2:  perf["1d"]  = round(float((s.iloc[-1] - s.iloc[-2])  / s.iloc[-2]  * 100), 2)
                if len(s) >= 5:  perf["5d"]  = round(float((s.iloc[-1] - s.iloc[-5])  / s.iloc[-5]  * 100), 2)
                if len(s) >= 20: perf["20d"] = round(float((s.iloc[-1] - s.iloc[-20]) / s.iloc[-20] * 100), 2)
                sector_perf[sector] = perf
            except Exception:
                pass
    except Exception:
        pass

    # ── Economic calendar ─────────────────────────────────────────────────────
    events = []
    try:
        cal = get_economic_calendar()
        if isinstance(cal, dict) and cal.get("economicCalendar"):
            events = [
                {"event": e.get("event"), "date": e.get("time"), "impact": e.get("impact")}
                for e in cal["economicCalendar"]
                if e.get("impact") in ("high", "medium") and e.get("country") == "US"
            ][:8]
    except Exception:
        pass

    data = {
        "vix":                  vix,
        "spy_above_50d":        spy_above_50d,
        "spy_above_200d":       spy_above_200d,
        "spy_roc_20d":          spy_roc_20d,
        "yield_spread_10y_3m":  yield_spread_10y_3m,
        "yield_curve_inverted": (yield_spread_10y_3m < 0) if yield_spread_10y_3m is not None else None,
        "usd_1w_change_pct":    usd_1w_change_pct,
        "sector_performance":   sector_perf,
        "upcoming_us_events":   events,
    }
    _cache = {"data": data, "ts": time.time()}
    return data


def get_vote(ticker: str) -> dict:
    try:
        macro = _get_macro_snapshot()

        # Pull ticker-specific sector performance
        ticker_sector = _TICKER_SECTOR.get(ticker.upper(), "Unknown")
        ticker_sector_perf = macro["sector_performance"].get(ticker_sector, {})

        market_data = {
            "ticker":                 ticker,
            "ticker_sector":          ticker_sector,
            "ticker_sector_perf":     ticker_sector_perf,
            "vix":                    macro["vix"],
            "spy_market_regime": {
                "above_50d_ma":  macro["spy_above_50d"],
                "above_200d_ma": macro["spy_above_200d"],
                "roc_20d_pct":   macro["spy_roc_20d"],
            },
            "yield_spread_10y_3m":    macro["yield_spread_10y_3m"],
            "yield_curve_inverted":   macro["yield_curve_inverted"],
            "usd_1w_change_pct":      macro["usd_1w_change_pct"],
            "all_sector_performance": macro["sector_performance"],
            "upcoming_us_events":     macro["upcoming_us_events"],
        }

        result = call_claude(
            SYSTEM_PROMPT,
            f"Macro analysis for {ticker}: {json.dumps(market_data)}",
            "macro_watcher",
        )
        # Inject raw fields the orchestrator needs for dynamic weight selection
        result["spy_above_200d"] = macro["spy_above_200d"]
        result["vix_raw"]        = macro["vix"]
        return result

    except Exception as e:
        return {
            "agent": "macro_watcher", "ticker": ticker,
            "action": "HOLD", "confidence": 0.0,
            "rationale": f"Data fetch failed: {e}",
            "suggested_position_size_pct": 0,
            "risk_off": False,
            "spy_above_200d": None,
            "vix_raw": None,
        }
