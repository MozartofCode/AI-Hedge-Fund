import json
from backend.agents.base_agent import call_claude
from backend.data.finnhub_client import (
    get_company_news, get_news_sentiment, get_insider_sentiment, get_earnings_surprise,
)

SYSTEM_PROMPT = """You are the Newshound on an AI trading committee. Analyze news sentiment, catalysts, and insider activity.
Return ONLY a valid JSON object — no markdown, no explanation, just JSON:
{
  "action": "BUY" | "SELL" | "HOLD",
  "confidence": 0.0-1.0,
  "rationale": "2-3 sentences citing specific news or sentiment data",
  "suggested_position_size_pct": 0-10
}
Key signals: overall news sentiment score, insider MSPR score (positive = insiders buying), earnings surprise from last quarter, any FDA/regulatory/legal red flags in headlines."""


def get_vote(ticker: str) -> dict:
    try:
        news = get_company_news(ticker, days=7)
        sentiment = get_news_sentiment(ticker)
        insider = get_insider_sentiment(ticker)
        earnings_surprise = get_earnings_surprise(ticker)

        # Top 5 headlines
        headlines = [
            {"headline": n.get("headline", ""), "source": n.get("source", "")}
            for n in news[:5]
        ]

        # Average MSPR (insider net buying score: -1 to +1)
        mspr = None
        if isinstance(insider, dict) and insider.get("data"):
            vals = [d.get("mspr") for d in insider["data"] if d.get("mspr") is not None]
            mspr = round(sum(vals) / len(vals), 4) if vals else None

        # Most recent earnings surprise
        latest_surprise = None
        if earnings_surprise:
            e = earnings_surprise[0]
            latest_surprise = {
                "actual": e.get("actual"),
                "estimate": e.get("estimate"),
                "surprise_pct": e.get("surprisePercent"),
            }

        market_data = {
            "ticker": ticker,
            "news_sentiment_score": sentiment.get("companyNewsScore"),
            "sector_avg_bullish_pct": sentiment.get("sectorAverageBullishPercent"),
            "article_buzz": sentiment.get("buzz", {}).get("buzz"),
            "recent_headlines": headlines,
            "insider_mspr": mspr,
            "latest_earnings_surprise": latest_surprise,
        }

        return call_claude(
            SYSTEM_PROMPT,
            f"News/sentiment analysis for {ticker}: {json.dumps(market_data)}",
            "newshound",
        )
    except Exception as e:
        return {
            "agent": "newshound", "ticker": ticker,
            "action": "HOLD", "confidence": 0.0,
            "rationale": f"Data fetch failed: {e}",
            "suggested_position_size_pct": 0,
        }
