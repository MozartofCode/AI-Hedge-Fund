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
            # ── Mega-cap tech / AI infrastructure ────────────────────────────
            "AAPL", "NVDA", "MSFT", "GOOGL", "META",
            "AMD", "ARM", "AVGO", "SMCI",
            # ── Cloud / cybersecurity / software ─────────────────────────────
            "CRWD", "NET", "DDOG", "PLTR", "GTLB",
            "APP", "TTD", "MNDY", "DUOL",
            # ── Consumer / e-commerce ─────────────────────────────────────────
            "AMZN", "TSLA", "CELH", "HIMS", "CAVA",
            # ── Fintech / crypto ──────────────────────────────────────────────
            "HOOD", "SOFI", "AFRM", "UPST", "NU",
            "COIN", "MARA", "MSTR",
            # ── Space / deep tech / AI hardware ──────────────────────────────
            "RKLB", "LUNR", "IONQ", "JOBY", "ASTS",
            "SOUN", "RXRX",
            # ── Financials ───────────────────────────────────────────────────
            "JPM", "GS",
            # ── Healthcare / biotech ─────────────────────────────────────────
            "LLY", "RDDT", "AXON",
            # ── Energy ───────────────────────────────────────────────────────
            "XOM", "CLSK",
            # ── Broad market ─────────────────────────────────────────────────
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
            "PETR4.SA",   # Petrobras — oil giant, high volatility
            "VALE3.SA",   # Vale — iron ore, global commodity play
            "ITUB4.SA",   # Itaú Unibanco — largest private bank
            "BBDC4.SA",   # Bradesco — banking
            "ABEV3.SA",   # Ambev — beverages
            "WEGE3.SA",   # WEG — industrial motors, exports heavily
            "RENT3.SA",   # Localiza — car rental leader
            "B3SA3.SA",   # B3 exchange itself
            "SUZB3.SA",   # Suzano — pulp & paper
            "MGLU3.SA",   # Magazine Luiza — e-commerce
            "RADL3.SA",   # Raia Drogasil — pharmacy chain
            "CASH3.SA",   # Méliuz — fintech/cashback
            "IFCM3.SA",   # Infracommerce — e-commerce tech
            "INTB3.SA",   # Intelbras — tech hardware
            "MXRF11.SA",  # Maxi Renda — REIT (FII)
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
            "YPF",    # YPF SA — oil & gas, high beta
            "GGAL",   # Grupo Financiero Galicia — banking
            "BMA",    # Banco Macro — retail banking
            "PAM",    # Pampa Energía — power generation
            "LOMA",   # Loma Negra — cement
            "TGS",    # Transportadora de Gas del Sur
            "CEPU",   # Central Puerto — electricity
            "SUPV",   # Grupo Supervielle — fintech bank
            "DESP",   # Despegar — Latin America travel
            "BIOX",   # Bioceres — ag-biotech, 10x candidate
            "GLOB",   # Globant — tech/software
            "MELI",   # MercadoLibre — Latin America Amazon
            "ARCO",   # Arcos Dorados — McDonald's franchisee
            "IRS",    # IRSA — real estate
            "CAAP",   # Corporación América — airports
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
            "THYAO.IS",  # Turkish Airlines — travel rebound
            "ASELS.IS",  # Aselsan — defense electronics
            "SISE.IS",   # Şişecam — glass & chemicals
            "KCHOL.IS",  # Koç Holding — conglomerate
            "GARAN.IS",  # Garanti BBVA — banking
            "AKBNK.IS",  # Akbank — banking
            "BIMAS.IS",  # BIM — discount retail
            "EREGL.IS",  # Ereğli Steel — steel producer
            "FROTO.IS",  # Ford Otosan — auto manufacturing
            "TCELL.IS",  # Turkcell — telecom
            "TOASO.IS",  # Tofaş — Fiat Türkiye
            "PGSUS.IS",  # Pegasus Airlines — budget carrier
            "EKGYO.IS",  # Emlak Konut — REIT
            "KOZAL.IS",  # Koza Altın — gold mining
            "SAHOL.IS",  # Sabancı Holding — conglomerate
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
            "MTNN.LG",       # MTN Nigeria — telco giant
            "DANGCEM.LG",    # Dangote Cement — largest cement producer
            "GTCO.LG",       # Guaranty Trust — banking
            "ZENITHBANK.LG", # Zenith Bank — tier-1 bank
            "AIRTELAFRI.LG", # Airtel Africa — telecom
            "ACCESSCORP.LG", # Access Holdings — banking
            "BUACEMENT.LG",  # BUA Cement — second largest cement
            "NB.LG",         # Nigerian Breweries — consumer staples
            "UBA.LG",        # United Bank for Africa — pan-African banking
            "SEPLAT.LG",     # Seplat Energy — oil & gas
            "FBNH.LG",       # First Bank Nigeria — legacy bank
            "STANBIC.LG",    # Stanbic IBTC — financial services
            "WAPCO.LG",      # Lafarge WAPCO — cement
            "DANGSUGAR.LG",  # Dangote Sugar — consumer goods
            "FIDSON.LG",     # Fidson Healthcare — pharma
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
