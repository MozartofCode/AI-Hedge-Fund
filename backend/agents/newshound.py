import json
import pandas as pd
import yfinance as yf
from backend.agents.base_agent import call_claude
from backend.data.finnhub_client import (
    get_company_news, get_news_sentiment, get_insider_sentiment, get_earnings_surprise,
)

SYSTEM_PROMPT = """You are the Newshound on an AI trading committee. Analyze news sentiment, catalysts, and market positioning.
Return ONLY a valid JSON object — no markdown, no explanation, just JSON:
{
  "action": "BUY" | "SELL" | "HOLD",
  "confidence": 0.0-1.0,
  "rationale": "2-3 sentences citing specific news or sentiment data",
  "suggested_position_size_pct": 0-10,
  "revisions_score": 0.0-1.0
}

revisions_score: analyst estimate revision trend — 1.0=strong positive revisions (many upgrades, multiple earnings beats with acceleration, high sentiment score, insider buying), 0.0=strong negative revisions (downgrades, misses, insider selling, red-flag headlines). 0.5=neutral/mixed.

Key signals:
- News sentiment score: >0.7 bullish, <0.3 bearish
- Insider MSPR: positive = insiders buying (strong bullish signal), negative = insiders selling (bearish)
- Earnings surprise trend: 3+ consecutive beats with acceleration = strong BUY signal; miss after beats = be cautious
- Article count: >20 articles in 14d signals heightened attention — amplifies direction
- Analyst upgrades (last 30 days): net positive = institutional confidence; net negative = concern
- SHORT INTEREST: >15% float shorted = high short interest. If positive catalyst present, short squeeze potential = very bullish. >30% = extreme squeeze risk.
- PUT/CALL RATIO: >1.2 = market is hedging heavily (bearish positioning or potential squeeze). <0.5 = bullish sentiment, calls dominating.
- Red flags in headlines: FDA rejection, lawsuit, SEC investigation, CEO departure, guidance cut → SELL with high confidence
- Positive catalysts: new product launch, major contract, acquisition at premium → BUY

Prefer SELL with low confidence over HOLD when bearish. Reserve HOLD for genuine neutrality."""


def get_vote(ticker: str) -> dict:
    try:
        news              = get_company_news(ticker, days=14)
        sentiment         = get_news_sentiment(ticker)
        insider           = get_insider_sentiment(ticker)
        earnings_surprise = get_earnings_surprise(ticker)

        # Top 15 headlines with timestamps
        headlines = [
            {"headline": n.get("headline", ""), "source": n.get("source", ""), "datetime": n.get("datetime", "")}
            for n in news[:15]
        ]

        # Average MSPR (insider net buying score: -1 to +1)
        mspr = None
        if isinstance(insider, dict) and insider.get("data"):
            vals = [d.get("mspr") for d in insider["data"] if d.get("mspr") is not None]
            mspr = round(sum(vals) / len(vals), 4) if vals else None

        # Last 4 earnings surprises (trend matters more than single quarter)
        earnings_history = []
        for e in earnings_surprise[:4]:
            earnings_history.append({
                "quarter":      e.get("period"),
                "actual":       e.get("actual"),
                "estimate":     e.get("estimate"),
                "surprise_pct": e.get("surprisePercent"),
            })

        # Analyst upgrades / downgrades — last 30 days only via yfinance
        upgrade_count   = 0
        downgrade_count = 0
        try:
            upgrades_df = yf.Ticker(ticker).upgrades_downgrades
            if upgrades_df is not None and not upgrades_df.empty:
                try:
                    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=30)
                    idx = upgrades_df.index
                    if idx.tz is None:
                        cutoff = cutoff.tz_localize(None)
                    recent_upgrades = upgrades_df[idx >= cutoff]
                except Exception:
                    recent_upgrades = upgrades_df.tail(10)
                upgrade_count   = int((recent_upgrades["Action"] == "up").sum())
                downgrade_count = int((recent_upgrades["Action"] == "down").sum())
        except Exception:
            pass

        # Short interest (% of float sold short)
        short_interest_pct = None
        try:
            info = yf.Ticker(ticker).info
            pct  = info.get("shortPercentOfFloat")
            if pct is not None:
                short_interest_pct = round(float(pct) * 100 if float(pct) <= 1.0 else float(pct), 2)
        except Exception:
            pass

        # Put/call ratio from nearest-expiry options chain
        put_call_ratio = None
        try:
            t    = yf.Ticker(ticker)
            opts = t.options
            if opts:
                chain      = t.option_chain(opts[0])
                calls_oi   = chain.calls["openInterest"].sum()
                puts_oi    = chain.puts["openInterest"].sum()
                if calls_oi > 0:
                    put_call_ratio = round(float(puts_oi / calls_oi), 2)
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
            "earnings_surprise_history": earnings_history,
            "analyst_upgrades_30d":      upgrade_count,
            "analyst_downgrades_30d":    downgrade_count,
            "analyst_net_sentiment":     upgrade_count - downgrade_count,
            "short_interest_pct":        short_interest_pct,
            "put_call_ratio":            put_call_ratio,
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
