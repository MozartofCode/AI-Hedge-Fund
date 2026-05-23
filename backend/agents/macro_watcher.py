"""
Macro Watcher agent — VIX, yield curve, USD, SPY trend, sector momentum, 10Y yield regime.
Round 3 additions: 10Y yield level + 1-week change (rate regime sensitivity),
sector leadership ranking (which sectors are hot), expanded ticker map for 25-ticker watchlist.
Cached 30 min so macro data is fetched once per session.
"""
import json
import time
import yfinance as yf
from backend.agents.base_agent import call_claude
from backend.data.indicators import calc_sma
from backend.data.finnhub_client import get_economic_calendar

SYSTEM_PROMPT = """You are the Macro Watcher on an AI investment committee hunting for 10X opportunities.
Return ONLY a valid JSON object — no markdown, no explanation, just JSON:
{
  "action": "BUY" | "SELL" | "HOLD",
  "confidence": 0.0-1.0,
  "rationale": "1 plain-English sentence — name the single most important macro signal (e.g. 'Interest rates are falling and the market is in a healthy uptrend, which is a good backdrop for growth stocks.')",
  "suggested_position_size_pct": 0-12,
  "risk_off": false
}

Set "risk_off": true if ANY of: VIX > 25, yield curve inverted, SPY below 200d MA, OR high-impact event within 2 days.

KEY SIGNALS (in priority order):

★ RATE REGIME (critical for growth stocks):
  - t10y_yield < 4.5% AND falling = IDEAL for high-growth/high-PE stocks. Maximize confidence.
  - t10y_yield rising fast (t10y_1w_change > +0.15%) = headwind for growth/high-PE stocks (NVDA, PLTR, CRWD). Reduce confidence.
  - t10y_yield > 5.0% = serious headwind for growth stocks. Prefer value/financials.
  - Falling 10Y + rising SPY = prime bull market for 10X candidates.

★ SECTOR LEADERSHIP (where is the hot money flowing?):
  - sector_leadership_rank shows which sectors lead on 20d performance. Top 2 sectors = where 10X candidates live now.
  - Technology in top 2 = green light for tech growth plays.
  - Defensive sectors (Utilities, Consumer Staples) leading = risk-off, market rotation out of growth.
  - Sector ETF in strong uptrend (20d > 5%) = tailwind for stocks in that sector.

MARKET REGIME (most important):
  - SPY above BOTH 50d and 200d MA = confirmed bull market (favor BUY, maximize position sizing)
  - SPY above 200d MA only = recovering bull (favor BUY with caution)
  - SPY below 200d MA = bear market (favor SELL/HOLD, risk_off = true)

VIX:
  - < 15 = calm market — ideal for building positions in growth stocks
  - 15-20 = normal range
  - 20-25 = elevated anxiety — reduce confidence
  - > 25 = risk-off, risk_off = true, prefer HOLD/SELL
  - > 35 = panic selling — potential contrarian BUY opportunity (ONLY for broad index)

YIELD CURVE (10Y - 3M): positive = healthy. Inverted (< 0) = recession risk (risk_off = true).
USD: 1w change > +1% = headwind for multinational earnings. Weakening USD = tailwind.
SECTOR MOMENTUM: Rising sector ETF (20d > +3%) = tailwind for stocks in that sector.
HIGH-IMPACT EVENTS within 2 days (Fed, CPI, NFP) = increase caution, risk_off = true.

Prefer SELL with low confidence over HOLD when bearish. Reserve HOLD for genuine neutrality."""

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

# Ticker → sector for full 25-ticker watchlist
_TICKER_SECTOR = {
    # Mega-cap tech / AI
    "AAPL":  "Technology", "NVDA":  "Technology", "MSFT": "Technology",
    "GOOGL": "Technology", "META":  "Technology", "AMD":  "Technology",
    "ARM":   "Technology", "AVGO":  "Technology", "SMCI": "Technology",
    # Cloud / cybersecurity / software
    "CRWD":  "Technology", "NET":   "Technology", "DDOG": "Technology",
    "PLTR":  "Technology",
    # Consumer
    "AMZN":  "Consumer Disc", "TSLA": "Consumer Disc",
    # Financials / fintech / crypto proxy
    "JPM":   "Financials", "GS":    "Financials",
    "HOOD":  "Financials", "SOFI":  "Financials", "MSTR": "Financials",
    # Healthcare
    "UNH":   "Healthcare", "LLY":   "Healthcare",
    # Energy
    "XOM":   "Energy",
    # Broad market
    "SPY":   "Broad Market", "QQQ":  "Technology",
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
    t10y_yield          = None
    t10y_1w_change      = None
    try:
        t3m  = yf.Ticker("^IRX").history(period="5d")["Close"].dropna()
        t10y = yf.Ticker("^TNX").history(period="10d")["Close"].dropna()
        if not t3m.empty and not t10y.empty:
            yield_spread_10y_3m = round(float(t10y.iloc[-1]) - float(t3m.iloc[-1]), 3)
        if not t10y.empty:
            t10y_yield = round(float(t10y.iloc[-1]), 3)
            if len(t10y) >= 5:
                t10y_1w_change = round(float(t10y.iloc[-1] - t10y.iloc[-5]), 3)
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

    # ── ★ Sector leadership rank (by 20d performance) ─────────────────────────
    sector_leadership_rank = []
    try:
        ranked = sorted(
            [(s, p.get("20d", 0)) for s, p in sector_perf.items() if "20d" in p],
            key=lambda x: x[1],
            reverse=True,
        )
        sector_leadership_rank = [{"sector": s, "20d_pct": round(p, 2)} for s, p in ranked]
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
        "vix":                     vix,
        "spy_above_50d":           spy_above_50d,
        "spy_above_200d":          spy_above_200d,
        "spy_roc_20d":             spy_roc_20d,
        "yield_spread_10y_3m":     yield_spread_10y_3m,
        "yield_curve_inverted":    (yield_spread_10y_3m < 0) if yield_spread_10y_3m is not None else None,
        "t10y_yield":              t10y_yield,             # ★ rate level
        "t10y_1w_change":          t10y_1w_change,         # ★ rate direction
        "usd_1w_change_pct":       usd_1w_change_pct,
        "sector_performance":      sector_perf,
        "sector_leadership_rank":  sector_leadership_rank, # ★ ranked by momentum
        "upcoming_us_events":      events,
    }
    _cache = {"data": data, "ts": time.time()}
    return data


def get_vote(ticker: str) -> dict:
    try:
        macro = _get_macro_snapshot()

        ticker_sector      = _TICKER_SECTOR.get(ticker.upper(), "Unknown")
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
            "t10y_yield":             macro["t10y_yield"],             # ★
            "t10y_1w_change":         macro["t10y_1w_change"],         # ★
            "usd_1w_change_pct":      macro["usd_1w_change_pct"],
            "sector_leadership_rank": macro["sector_leadership_rank"], # ★
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
