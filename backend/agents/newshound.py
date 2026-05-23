import json
import yfinance as yf
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
Key signals:
- News sentiment score: >0.7 bullish, <0.3 bearish
- Insider MSPR score: positive = insiders buying (strong bullish), negative = insiders selling (bearish)
- Earnings surprise: beat by >5% = bullish catalyst; miss = bearish
- Article count: high volume of coverage (>20 articles in 14d) signals heightened attention — can amplify any direction
- Analyst upgrades vs downgrades: net positive (more upgrades) = institutional confidence; net negative = concern
- Red flags in headlines: FDA rejection, lawsuit, SEC investigation, CEO departure, guidance cut = lower confidence or SELL"""


def get_vote(ticker: str) -> dict:
    try:
        news              = get_company_news(ticker, days=14)
        sentiment         = get_news_sentiment(ticker)
        insider           = get_insider_sentiment(ticker)
        earnings_surprise = get_earnings_surprise(ticker)

        # Top 15 headlines with timestamps
        headlines = [
            {
                "headline":  n.get("headline", ""),
                "source":    n.get("source", ""),
                "datetime":  n.get("datetime", ""),
            }
            for n in news[:15]
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
                "actual":       e.get("actual"),
                "estimate":     e.get("estimate"),
                "surprise_pct": e.get("surprisePercent"),
            }

        # Analyst upgrades / downgrades via yfinance (free, no extra API key)
        upgrade_count   = 0
        downgrade_count = 0
        try:
            upgrades_df = yf.Ticker(ticker).upgrades_downgrades
            if upgrades_df is not None and not upgrades_df.empty:
                recent_actions = upgrades_df.tail(10)
                upgrade_count   = int((recent_actions["Action"] == "up").sum())
                downgrade_count = int((recent_actions["Action"] == "down").sum())
        except Exception:
            pass

        market_data = {
            "ticker":                    ticker,
            "news_sentiment_score":      sentiment.get("companyNewsScore"),
            "sector_avg_bullish_pct":    sentiment.get("sectorAverageBullishPercent"),
            "article_buzz":              sentiment.get("buzz", {}).get("buzz"),
            "article_count_14d":         len(news),
            "recent_headlines":          headlines,
            "insider_mspr":              mspr,
            "latest_earnings_surprise":  latest_surprise,
            "analyst_upgrades_recent":   upgrade_count,
            "analyst_downgrades_recent": downgrade_count,
            "analyst_net_sentiment":     upgrade_count - downgrade_count,
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
