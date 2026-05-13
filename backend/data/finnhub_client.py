import os
import time
from datetime import datetime, timedelta
import finnhub
from dotenv import load_dotenv

load_dotenv()

_client = finnhub.Client(api_key=os.getenv("FINNHUB_API_KEY", ""))


def _sleep():
    time.sleep(1)  # 60 calls/min free tier guard


def get_company_news(ticker: str, days: int = 7) -> list:
    _sleep()
    try:
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        news = _client.company_news(ticker, _from=start, to=end)
        return news[:10] if news else []
    except Exception:
        return []


def get_news_sentiment(ticker: str) -> dict:
    _sleep()
    try:
        return _client.news_sentiment(ticker) or {}
    except Exception:
        return {}


def get_insider_sentiment(ticker: str) -> dict:
    _sleep()
    try:
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        return _client.insider_sentiment(ticker, _from=start, to=end) or {}
    except Exception:
        return {}


def get_earnings_surprise(ticker: str) -> list:
    _sleep()
    try:
        data = _client.company_earnings(ticker, limit=4)
        return data or []
    except Exception:
        return []


def get_economic_calendar() -> dict:
    _sleep()
    try:
        end = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
        start = datetime.now().strftime("%Y-%m-%d")
        return _client.economic_calendar(_from=start, to=end) or {}
    except Exception:
        return {}
