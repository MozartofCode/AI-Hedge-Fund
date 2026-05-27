"""
Market configuration for all 5 supported exchanges.
Each market has its own watchlist, hours, currency, and starting capital.
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
    "BR": {
        "name":            "Brazil",
        "exchange":        "B3",
        "flag":            "🇧🇷",
        "currency_symbol": "R$",
        "currency_code":   "BRL",
        "starting_cash":   5_000_000.0,   # ~$1M USD equiv
        "timezone":        "America/Sao_Paulo",
        "open":            dtime(10, 0),
        "close":           dtime(17, 30),
        "slack_notify":    False,
        # Full seed list lives in backend/screener.py (_BR_SEEDS)
        "watchlist": [
            "PETR4.SA","VALE3.SA","ITUB4.SA","BBDC4.SA","ABEV3.SA",
            "WEGE3.SA","RENT3.SA","B3SA3.SA","SUZB3.SA","MGLU3.SA",
            "RADL3.SA","CASH3.SA","IFCM3.SA","INTB3.SA","MXRF11.SA",
            "PRIO3.SA","CSAN3.SA","EMBR3.SA","BEEF3.SA","CPLE6.SA",
            "VIVT3.SA","NTCO3.SA","SOMA3.SA","ARZZ3.SA","SRNA3.SA",
        ],
    },
    "AR": {
        "name":            "Argentina",
        "exchange":        "BYMA / NYSE ADRs",
        "flag":            "🇦🇷",
        "currency_symbol": "$",
        "currency_code":   "USD",           # ADRs trade in USD
        "starting_cash":   1_000_000.0,
        "timezone":        "America/Argentina/Buenos_Aires",
        "open":            dtime(11, 0),
        "close":           dtime(17, 0),
        "slack_notify":    False,
        # NYSE/NASDAQ-listed Argentine ADRs — full seed list in backend/screener.py
        "watchlist": [
            "YPF","GGAL","BMA","PAM","LOMA","TGS","CEPU","SUPV","DESP","BIOX",
            "GLOB","MELI","ARCO","IRS","CAAP","IRCP","EDN","COME","AGRO",
        ],
    },
    "TR": {
        "name":            "Turkey",
        "exchange":        "BIST",
        "flag":            "🇹🇷",
        "currency_symbol": "₺",
        "currency_code":   "TRY",
        "starting_cash":   35_000_000.0,  # ~$1M USD equiv
        "timezone":        "Europe/Istanbul",
        "open":            dtime(10, 0),
        "close":           dtime(18, 0),
        "slack_notify":    False,
        # Full seed list in backend/screener.py (_TR_SEEDS)
        "watchlist": [
            "THYAO.IS","ASELS.IS","SISE.IS","KCHOL.IS","GARAN.IS",
            "AKBNK.IS","BIMAS.IS","EREGL.IS","FROTO.IS","TCELL.IS",
            "TOASO.IS","PGSUS.IS","EKGYO.IS","KOZAL.IS","SAHOL.IS",
            "TUPRS.IS","ARCLK.IS","SODA.IS","TAVHL.IS","ULKER.IS",
        ],
    },
    "NG": {
        "name":            "Nigeria",
        "exchange":        "NGX",
        "flag":            "🇳🇬",
        "currency_symbol": "₦",
        "currency_code":   "NGN",
        "starting_cash":   1_500_000_000.0,  # ~$1M USD equiv
        "timezone":        "Africa/Lagos",
        "open":            dtime(10, 30),
        "close":           dtime(14, 30),
        "slack_notify":    False,
        # Full seed list in backend/screener.py (_NG_SEEDS)
        "watchlist": [
            "MTNN.LG","DANGCEM.LG","GTCO.LG","ZENITHBANK.LG","AIRTELAFRI.LG",
            "ACCESSCORP.LG","BUACEMENT.LG","NB.LG","UBA.LG","SEPLAT.LG",
            "FBNH.LG","STANBIC.LG","WAPCO.LG","DANGSUGAR.LG","FIDSON.LG",
            "OANDO.LG","NESTLE.LG","PRESCO.LG","TOTAL.LG","CONOIL.LG",
        ],
    },
}

ALL_MARKET_CODES = list(MARKETS.keys())


def get_market(code: str) -> dict:
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
