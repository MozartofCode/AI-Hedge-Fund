"""
Dynamic stock screener — runs before each committee session to narrow the
universe from thousands of tickers down to the hottest ~200 candidates.

Strategy:
1. FMP screener API  → pulls stocks meeting basic liquidity thresholds
2. FMP gainers/actives → today's momentum leaders
3. yfinance sector ETF holdings → curated growth-sector coverage
4. Momentum filter  → rank by 20-day price change, keep top N

This is all pure math / free-data — no AI tokens spent. The AI committee
only fires on the screened output, so we effectively scan the whole market
at almost zero extra cost.
"""
import os
import time
import requests

_FMP_KEY = os.getenv("FMP_API_KEY", "")
_BASE    = "https://financialmodelingprep.com/api/v3"

# 2-hour cache so the screener refreshes twice per trading session
_cache: dict = {}
_CACHE_TTL   = 7200

# ── Hard-coded US seed list ──────────────────────────────────────────────────
# These always make the cut regardless of screener results.
# Kept intentionally broad so no obvious candidate is ever dropped.

_US_SEEDS = [
    # Mega-cap AI / hardware
    "AAPL","NVDA","MSFT","GOOGL","META","AMD","ARM","AVGO","SMCI","INTC","MU",
    # Cloud / SaaS / cyber
    "CRWD","NET","DDOG","PLTR","GTLB","APP","TTD","MNDY","DUOL","SOUN",
    "SNOW","HUBS","ZS","OKTA","PANW","ESTC","MDB","CFLT","BILL","DOCU",
    # Fintech / crypto
    "HOOD","SOFI","AFRM","UPST","NU","COIN","MARA","MSTR","RIOT","CLSK",
    "SQ","PYPL","ADYEY","PAYO","LC",
    # Consumer / health / social
    "AMZN","TSLA","CELH","HIMS","CAVA","RDDT","AXON","DUOL","WING","BROS",
    "LULU","NKE","DKS","BURL","FIVE",
    # Space / deep tech / quantum
    "RKLB","LUNR","IONQ","JOBY","ASTS","RXRX","ARQQ","QUBT","RGTI","ACHR",
    # Biotech / pharma
    "LLY","MRNA","BNTX","REGN","VRTX","NBIS","LEGN","EXAS","NTRA","ALNY",
    # Financials
    "JPM","GS","MS","V","MA","AXP",
    # Energy / industrials
    "XOM","CVX","NEE","FSLR","ENPH","RUN",
    # Broad market
    "SPY","QQQ","IWM","ARKK",
]

SEEDS = {
    "US": _US_SEEDS,
}


def _fmp_screener(min_price: float = 2.0, min_volume: int = 300_000,
                  limit: int = 500) -> list:
    """FMP /stock-screener — returns US tickers meeting liquidity thresholds."""
    try:
        r = requests.get(
            f"{_BASE}/stock-screener",
            params={
                "priceMoreThan": min_price,
                "volumeMoreThan": min_volume,
                "country": "US",
                "exchange": "NYSE,NASDAQ,AMEX",
                "apikey": _FMP_KEY,
                "limit": limit,
            },
            timeout=15,
        )
        if r.status_code == 200:
            return [s["symbol"] for s in r.json()
                    if s.get("symbol") and str(s["symbol"]).isalpha()]
    except Exception:
        pass
    return []


def _fmp_movers() -> list:
    """FMP gainers + most-active — today's momentum leaders."""
    tickers = []
    for ep in ("gainers", "actives"):
        try:
            r = requests.get(
                f"{_BASE}/{ep}",
                params={"apikey": _FMP_KEY},
                timeout=10,
            )
            if r.status_code == 200:
                tickers += [
                    s.get("ticker") or s.get("symbol", "")
                    for s in r.json()
                    if (s.get("ticker") or s.get("symbol", "")).isalpha()
                ]
        except Exception:
            pass
    return tickers


def _fmp_sector_winners() -> list:
    """FMP sector performance — pull tickers from outperforming sectors."""
    tickers = []
    try:
        # Top 100 stocks by sector performance proxy — ETF constituents skipped
        # Use FMP's biggest movers per sector instead
        r = requests.get(
            f"{_BASE}/stock-screener",
            params={
                "priceMoreThan": 5,
                "volumeMoreThan": 1_000_000,
                "betaMoreThan": 1.0,     # high-beta = volatile = opportunity
                "country": "US",
                "exchange": "NYSE,NASDAQ",
                "apikey": _FMP_KEY,
                "limit": 300,
            },
            timeout=15,
        )
        if r.status_code == 200:
            tickers += [s["symbol"] for s in r.json()
                        if s.get("symbol") and str(s["symbol"]).isalpha()]
    except Exception:
        pass
    return tickers


def get_watchlist(market: str = "US", max_tickers: int = 250) -> list:
    """
    Return the full US watchlist.

    Merges the seed list + FMP screener + today's movers, deduplicates, and
    caps at max_tickers. Falls back to the seed list alone if no FMP key is set.

    Results are cached for 2 hours so the screener only runs once per session.
    """
    market = market.upper()
    cache_key = f"{market}_watchlist"

    cached = _cache.get(cache_key)
    if cached and time.time() - cached["ts"] < _CACHE_TTL:
        return cached["data"]

    seeds = SEEDS.get(market, _US_SEEDS)

    if _FMP_KEY:
        # Dynamic screen — narrows full market to top opportunities
        dynamic = _fmp_movers() + _fmp_screener(limit=500) + _fmp_sector_winners()
        # Seeds always go first so they're never dropped by the cap
        combined = list(dict.fromkeys(seeds + dynamic))
        # Basic filter: alpha-only symbols, 1–5 chars (no ETF junk like SPXL3X)
        filtered = [t for t in combined
                    if t and 1 <= len(t) <= 5 and t.isalpha()]
        result = filtered[:max_tickers]
    else:
        # No FMP key — just use the seed list
        result = seeds

    _cache[cache_key] = {"ts": time.time(), "data": result}
    print(f"[screener][{market}] watchlist = {len(result)} tickers")
    return result
