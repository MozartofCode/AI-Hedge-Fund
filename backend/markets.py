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
        "watchlist": [
            "AAPL", "NVDA", "MSFT", "GOOGL",
            "AMD", "ARM", "AVGO", "SMCI",
            "META", "PLTR", "CRWD", "NET", "DDOG",
            "AMZN", "TSLA",
            "JPM", "GS", "HOOD", "SOFI", "MSTR",
            "UNH", "LLY",
            "XOM",
            "SPY", "QQQ",
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
        "watchlist": [
            "PETR4.SA",   # Petrobras
            "VALE3.SA",   # Vale
            "ITUB4.SA",   # Itaú Unibanco
            "BBDC4.SA",   # Bradesco
            "ABEV3.SA",   # Ambev
            "WEGE3.SA",   # WEG Equipamentos
            "RENT3.SA",   # Localiza
            "B3SA3.SA",   # B3 exchange itself
            "SUZB3.SA",   # Suzano Papel
            "MGLU3.SA",   # Magazine Luiza
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
        # Using NYSE/NASDAQ-listed Argentine ADRs for best data quality
        "watchlist": [
            "YPF",    # YPF SA (oil & gas)
            "GGAL",   # Grupo Financiero Galicia
            "BMA",    # Banco Macro
            "PAM",    # Pampa Energía
            "LOMA",   # Loma Negra (cement)
            "TGS",    # Transportadora de Gas del Sur
            "CEPU",   # Central Puerto (power)
            "SUPV",   # Grupo Supervielle
            "DESP",   # Despegar (travel)
            "BIOX",   # Bioceres Crop Solutions
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
        "watchlist": [
            "THYAO.IS",  # Turkish Airlines
            "ASELS.IS",  # Aselsan (defense)
            "SISE.IS",   # Şişecam (glass)
            "KCHOL.IS",  # Koç Holding
            "GARAN.IS",  # Garanti BBVA
            "AKBNK.IS",  # Akbank
            "BIMAS.IS",  # BIM (retail)
            "EREGL.IS",  # Ereğli Steel
            "FROTO.IS",  # Ford Otosan
            "TCELL.IS",  # Turkcell
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
        # NGX tickers — data availability varies by broker/source
        "watchlist": [
            "MTNN.LG",       # MTN Nigeria
            "DANGCEM.LG",    # Dangote Cement
            "GTCO.LG",       # Guaranty Trust
            "ZENITHBANK.LG", # Zenith Bank
            "AIRTELAFRI.LG", # Airtel Africa
            "ACCESSCORP.LG", # Access Holdings
            "BUACEMENT.LG",  # BUA Cement
            "NB.LG",         # Nigerian Breweries
            "UBA.LG",        # United Bank for Africa
            "SEPLAT.LG",     # Seplat Energy
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
