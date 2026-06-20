"""
Market configuration for the US stock market (NYSE / NASDAQ).
This is a US-only AI hedge fund — no other exchanges are supported.
"""
import pytz
from datetime import datetime, time as dtime

MARKETS = {
    "US": {
        "name":            "United States",
        "exchange":        "NYSE / NASDAQ",
        "flag":            "🇺🇸",
        "currency_symbol": "$",
        "currency_code":   "USD",
        "starting_cash":   1_000_000.0,
        "timezone":        "America/New_York",
        "open":            dtime(9, 30),
        "close":           dtime(16, 0),
        "slack_notify":    True,
        # Static watchlist is the fallback seed — the screener dynamically
        # expands this to 200+ tickers per session using FMP + yfinance.
        # See backend/screener.py for the full seed list and dynamic logic.
        "watchlist": [
            "AAPL","NVDA","MSFT","GOOGL","META","AMD","ARM","AVGO","SMCI",
            "CRWD","NET","DDOG","PLTR","GTLB","APP","TTD","MNDY","DUOL","SOUN",
            "RKLB","LUNR","IONQ","JOBY","ASTS","RXRX",
            "AMZN","TSLA","CELH","HIMS","CAVA","LLY","RDDT","AXON",
            "HOOD","SOFI","AFRM","UPST","NU","COIN","MARA","MSTR",
            "JPM","GS","XOM","CLSK","SPY","QQQ",
        ],
    },
}

ALL_MARKET_CODES = list(MARKETS.keys())


def get_market(code: str = "US") -> dict:
    return MARKETS.get(code.upper(), MARKETS["US"])


def is_market_open(code: str = "US") -> bool:
    """Check if the given market is currently in its trading session."""
    cfg = get_market(code)
    try:
        tz  = pytz.timezone(cfg["timezone"])
        now = datetime.now(tz)
        if now.weekday() >= 5:   # Saturday / Sunday
            return False
        t = now.time().replace(second=0, microsecond=0)
        return cfg["open"] <= t <= cfg["close"]
    except Exception:
        return False


def get_market_display(code: str) -> str:
    cfg = get_market(code)
    return f"{cfg['flag']} {cfg['name']}"
