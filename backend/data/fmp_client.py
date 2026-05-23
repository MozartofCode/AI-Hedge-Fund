import os
import httpx
from dotenv import load_dotenv

load_dotenv()

_FMP_KEY = os.getenv("FMP_API_KEY", "")
_BASE = "https://financialmodelingprep.com/api/v3"


def _get(endpoint: str, params: dict = None):
    try:
        p = params or {}
        p["apikey"] = _FMP_KEY
        resp = httpx.get(f"{_BASE}/{endpoint}", params=p, timeout=30)
        return resp.json()
    except Exception:
        return {}


def get_profile(ticker: str) -> dict:
    data = _get(f"profile/{ticker}")
    return data[0] if isinstance(data, list) and data else {}


def get_income_statement(ticker: str, limit: int = 4) -> list:
    data = _get(f"income-statement/{ticker}", {"limit": limit})
    return data if isinstance(data, list) else []


def get_balance_sheet(ticker: str, limit: int = 2) -> list:
    data = _get(f"balance-sheet-statement/{ticker}", {"limit": limit})
    return data if isinstance(data, list) else []


def get_cash_flow(ticker: str, limit: int = 4) -> list:
    data = _get(f"cash-flow-statement/{ticker}", {"limit": limit})
    return data if isinstance(data, list) else []


def get_analyst_ratings(ticker: str) -> dict:
    data = _get(f"analyst-stock-recommendations/{ticker}", {"limit": 1})
    return data[0] if isinstance(data, list) and data else {}


def get_earnings_calendar(ticker: str) -> list:
    data = _get(f"historical/earning_calendar/{ticker}", {"limit": 4})
    return data if isinstance(data, list) else []


def get_analyst_price_target(ticker: str) -> dict:
    """Consensus analyst price target (high / low / consensus / median)."""
    data = _get("price-target-consensus", {"symbol": ticker})
    return data[0] if isinstance(data, list) and data else {}
