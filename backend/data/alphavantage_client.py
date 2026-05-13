import os
import httpx
from dotenv import load_dotenv

load_dotenv()

_AV_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "")
_BASE = "https://www.alphavantage.co/query"


def _get(params: dict) -> dict:
    try:
        params["apikey"] = _AV_KEY
        resp = httpx.get(_BASE, params=params, timeout=30)
        return resp.json()
    except Exception:
        return {}


def _latest(data: dict, series_key: str) -> dict:
    series = data.get(series_key, {})
    if not series:
        return {}
    return series[max(series.keys())]


def get_rsi(ticker: str) -> dict:
    data = _get({"function": "RSI", "symbol": ticker, "interval": "daily",
                 "time_period": 14, "series_type": "close"})
    return _latest(data, "Technical Analysis: RSI")


def get_macd(ticker: str) -> dict:
    data = _get({"function": "MACD", "symbol": ticker, "interval": "daily",
                 "series_type": "close"})
    return _latest(data, "Technical Analysis: MACD")


def get_sma(ticker: str, period: int) -> dict:
    data = _get({"function": "SMA", "symbol": ticker, "interval": "daily",
                 "time_period": period, "series_type": "close"})
    return _latest(data, "Technical Analysis: SMA")


def get_bbands(ticker: str) -> dict:
    data = _get({"function": "BBANDS", "symbol": ticker, "interval": "daily",
                 "time_period": 20, "series_type": "close"})
    return _latest(data, "Technical Analysis: BBANDS")


def get_sector_performance() -> dict:
    return _get({"function": "SECTOR"})


def get_global_quote(ticker: str) -> dict:
    data = _get({"function": "GLOBAL_QUOTE", "symbol": ticker})
    return data.get("Global Quote", {})
