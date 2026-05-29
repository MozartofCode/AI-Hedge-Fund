import os
import httpx
from dotenv import load_dotenv

load_dotenv()

_FMP_KEY = os.getenv("FMP_API_KEY", "")
_BASE = "https://financialmodelingprep.com/api/v3"


def _get(endpoint: str, params: dict = None):
    """
    Make a GET request to FMP v3 API.
    Returns the parsed JSON or {} / [] on error.
    Logs clearly when FMP returns an error message so Railway logs surface issues.
    """
    try:
        p = dict(params or {})   # copy so we never mutate caller's dict
        p["apikey"] = _FMP_KEY
        resp = httpx.get(f"{_BASE}/{endpoint}", params=p, timeout=30)
        data = resp.json()
        # FMP returns {"Error Message": "..."} when the key is invalid or
        # the endpoint is not available on the current plan.
        if isinstance(data, dict) and ("Error Message" in data or "message" in data):
            msg = data.get("Error Message") or data.get("message", "unknown FMP error")
            print(f"[FMP] /{endpoint} → error: {msg}")
            return {}
        return data
    except Exception as e:
        print(f"[FMP] /{endpoint} → exception: {e}")
        return {}


def get_profile(ticker: str) -> dict:
    data = _get(f"profile/{ticker}")
    return data[0] if isinstance(data, list) and data else {}


def get_income_statement(ticker: str, limit: int = 8) -> list:
    """Quarterly income statements — needed for QoQ/YoY acceleration metrics."""
    data = _get(f"income-statement/{ticker}", {"period": "quarter", "limit": limit})
    return data if isinstance(data, list) else []


def get_balance_sheet(ticker: str, limit: int = 4) -> list:
    """Quarterly balance sheets."""
    data = _get(f"balance-sheet-statement/{ticker}", {"period": "quarter", "limit": limit})
    return data if isinstance(data, list) else []


def get_cash_flow(ticker: str, limit: int = 8) -> list:
    """Quarterly cash flow statements."""
    data = _get(f"cash-flow-statement/{ticker}", {"period": "quarter", "limit": limit})
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


def get_analyst_price_targets(ticker: str, limit: int = 20) -> list:
    """Individual analyst price targets with firm names — for trust-weighted consensus."""
    data = _get("price-target", {"symbol": ticker, "limit": limit})
    return data if isinstance(data, list) else []


def get_dcf(ticker: str) -> dict:
    """FMP discounted cash flow intrinsic value estimate."""
    data = _get(f"discounted-cash-flow/{ticker}")
    return data[0] if isinstance(data, list) and data else {}


def search_ticker(query: str, limit: int = 8) -> list:
    """Search for tickers by name or symbol — used for name-to-ticker resolution."""
    data = _get("search", {"query": query, "limit": limit, "exchange": "NASDAQ,NYSE,AMEX"})
    return data if isinstance(data, list) else []
