"""
Newshound agent — Finnhub news/sentiment + yfinance options/short data.
Round 3 additions: consecutive earnings beats, squeeze risk score,
days-to-cover, sentiment divergence (contrarian accumulation signal).
"""
import json
import time
import pandas as pd
import yfinance as yf
from backend.agents.base_agent import call_claude
from backend.data.finnhub_client import (
    get_company_news, get_news_sentiment, get_insider_sentiment, get_earnings_surprise,
)

# Per-ticker cache — news doesn't change minute-to-minute
_cache: dict = {}
_CACHE_TTL = 7200  # 2 hours

SYSTEM_PROMPT = """You are the Newshound on an AI investment committee hunting for 10X opportunities.
Return ONLY a valid JSON object — no markdown, no explanation, just JSON:
{
  "action": "BUY" | "SELL" | "HOLD",
  "confidence": 0.0-1.0,
  "rationale": "1 plain-English sentence — name the single most important news or sentiment signal (e.g. 'Beat earnings 3 times in a row and analysts are raising price targets after last week's product launch.')",
  "suggested_position_size_pct": 0-12,
  "revisions_score": 0.0-1.0
}

revisions_score: analyst estimate revision trend — 1.0=strong upgrades + consecutive earnings beats + insider buying + positive catalyst, 0.0=downgrades + misses + insider selling + red flags. 0.5=neutral.

PRIORITY SIGNALS for 10X identification:

★ CONSECUTIVE EARNINGS BEATS (consecutive_beats): The most reliable 10X confirmation signal.
  - 1 beat: noise. 2 beats: pattern. 3+ beats: CONFIRMED growth inflection = strong BUY.
  - 3+ consecutive beats = raise confidence significantly. 4+ = maximum confidence.
  - Combine with "acceleration" in beat sizes (beating by more each quarter) = highest signal.

★ SQUEEZE RISK SCORE (squeeze_risk_score, 0-8 scale):
  - Score > 5 with a positive catalyst (earnings beat, upgrade, product launch) = EXPLOSIVE move potential.
  - Score > 3 = elevated squeeze risk, BUY with moderate confidence.
  - Mechanism: shorts forced to cover → buying frenzy → 2-5x move possible in days.
  - days_to_cover > 5 + short_interest > 20% = dangerous short position = squeeze setup.

★ SENTIMENT DIVERGENCE (sentiment_divergence=True): CONTRARIAN SIGNAL.
  - Negative mainstream news sentiment + positive insider buying = smart money accumulating while retail sells.
  - This setup precedes major reversals and is a classic 10X entry point.
  - Act on it: institutions buy what media hates.

★ INSIDER BUYING (insider_mspr): Insiders know more than anyone.
  - mspr > 0.5 = heavy net buying = very high conviction signal (BUY)
  - mspr > 0.2 = mild net buying (mildly bullish)
  - mspr < -0.3 = insiders selling = bearish warning
  - Combined with 3+ consecutive beats = near-certain institutional attention incoming

Standard signals:
- News sentiment score: >0.7 bullish, <0.3 bearish
- Article count 14d: >20 = heightened attention (amplifies direction)
- Analyst upgrades vs downgrades (30d): net positive = institutional confidence
- SHORT INTEREST: >15% = high. >30% = extreme. Alone = risky, but with catalyst = opportunity.
- PUT/CALL RATIO: >1.2 = hedging. >2.0 = capitulation/extreme fear (potential squeeze). <0.5 = bullish positioning.
- Red flags: FDA rejection, SEC investigation, CEO departure, guidance cut → SELL high confidence
- Positive catalysts: new product launch, contract win, acquisition premium → BUY

★ UNUSUAL CALL ACTIVITY (unusual_call_activity, call_vol_to_oi):
  - unusual_call_activity=True means >30% of total call open interest traded in a single session.
  - This is the options market equivalent of a block trade — informed money positioning ahead of a move.
  - unusual_call_activity=True + positive catalyst (earnings soon, product launch) = HIGH conviction BUY.
  - call_vol_to_oi > 0.5 = extremely unusual — institutions rarely buy this aggressively unless they know something.

Prefer SELL with low confidence over HOLD when bearish. Reserve HOLD for genuine neutrality."""


def get_vote(ticker: str) -> dict:
    # Return cached result if fresh enough
    cached = _cache.get(ticker)
    if cached and time.time() - cached["ts"] < _CACHE_TTL:
        return cached["data"]

    try:
        news              = get_company_news(ticker, days=14)
        sentiment         = get_news_sentiment(ticker)
        insider           = get_insider_sentiment(ticker)
        earnings_surprise = get_earnings_surprise(ticker)

        # Top 15 headlines
        headlines = [
            {"headline": n.get("headline", ""), "source": n.get("source", ""), "datetime": n.get("datetime", "")}
            for n in news[:15]
        ]

        # Average MSPR (insider net buying score: -1 to +1)
        mspr = None
        if isinstance(insider, dict) and insider.get("data"):
            vals = [d.get("mspr") for d in insider["data"] if d.get("mspr") is not None]
            mspr = round(sum(vals) / len(vals), 4) if vals else None

        # Last 4 earnings surprises
        earnings_history = []
        for e in earnings_surprise[:4]:
            earnings_history.append({
                "quarter":      e.get("period"),
                "actual":       e.get("actual"),
                "estimate":     e.get("estimate"),
                "surprise_pct": e.get("surprisePercent"),
            })

        # ★ Consecutive earnings beats (key 10X confirmation)
        consecutive_beats = 0
        try:
            for e in earnings_history:
                surprise = e.get("surprise_pct")
                if surprise is not None and float(surprise) > 0:
                    consecutive_beats += 1
                else:
                    break
        except Exception:
            pass

        # Analyst upgrades / downgrades — last 30 days
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

        # Short interest, days to cover, put/call — single yfinance .info call
        short_interest_pct = None
        days_to_cover      = None
        try:
            info = yf.Ticker(ticker).info
            pct  = info.get("shortPercentOfFloat")
            if pct is not None:
                short_interest_pct = round(float(pct) * 100 if float(pct) <= 1.0 else float(pct), 2)
            # Days to cover = shares short / avg daily volume
            shares_short = info.get("sharesShort")
            avg_vol      = info.get("averageVolume10days") or info.get("averageVolume")
            if shares_short and avg_vol and avg_vol > 0:
                days_to_cover = round(shares_short / avg_vol, 1)
        except Exception:
            pass

        # Put/call ratio + unusual call activity from nearest-expiry options chain
        put_call_ratio        = None
        unusual_call_activity = False
        call_vol_to_oi        = None
        try:
            t    = yf.Ticker(ticker)
            opts = t.options
            if opts:
                # Aggregate across nearest 2 expirations
                total_call_vol = 0
                total_call_oi  = 0
                total_puts_oi  = 0
                for exp in opts[:2]:
                    chain = t.option_chain(exp)
                    total_call_vol += int(chain.calls["volume"].fillna(0).sum())
                    total_call_oi  += int(chain.calls["openInterest"].fillna(0).sum())
                    total_puts_oi  += int(chain.puts["openInterest"].fillna(0).sum())
                if total_call_oi > 0:
                    put_call_ratio = round(float(total_puts_oi / total_call_oi), 2)
                    # Volume-to-OI ratio: how much of outstanding contracts traded today
                    call_vol_to_oi = round(total_call_vol / total_call_oi, 3)
                    # Unusual = >30% of open interest traded in a single day + meaningful volume
                    unusual_call_activity = bool(call_vol_to_oi > 0.30 and total_call_vol > 500)
        except Exception:
            pass

        # ★ Squeeze risk score (0-8): higher = more explosive squeeze potential
        squeeze_risk_score = None
        try:
            if short_interest_pct is not None and short_interest_pct > 8:
                score = 0.0
                if short_interest_pct > 30:  score += 3
                elif short_interest_pct > 20: score += 2
                elif short_interest_pct > 10: score += 1
                if consecutive_beats >= 3:   score += 2
                elif consecutive_beats >= 2: score += 1
                if mspr is not None and mspr > 0.3: score += 2
                if put_call_ratio is not None and put_call_ratio > 1.5: score += 1
                if days_to_cover is not None and days_to_cover > 5: score += 1
                squeeze_risk_score = round(min(score, 8.0), 1)
        except Exception:
            pass

        # ★ Sentiment divergence: bearish news + insider buying = contrarian accumulation
        sentiment_divergence = False
        try:
            news_score = sentiment.get("companyNewsScore") or 0.5
            if float(news_score) < 0.35 and mspr is not None and mspr > 0.25:
                sentiment_divergence = True
        except Exception:
            pass

        market_data = {
            "ticker":                    ticker,
            # Sentiment
            "news_sentiment_score":      sentiment.get("companyNewsScore"),
            "sector_avg_bullish_pct":    sentiment.get("sectorAverageBullishPercent"),
            "article_buzz":              sentiment.get("buzz", {}).get("buzz"),
            "article_count_14d":         len(news),
            "recent_headlines":          headlines,
            # Insider
            "insider_mspr":              mspr,
            # ★ Earnings inflection signals
            "earnings_surprise_history": earnings_history,
            "consecutive_beats":         consecutive_beats,   # ★
            # Analyst
            "analyst_upgrades_30d":      upgrade_count,
            "analyst_downgrades_30d":    downgrade_count,
            "analyst_net_sentiment":     upgrade_count - downgrade_count,
            # ★ Squeeze signals
            "short_interest_pct":        short_interest_pct,
            "days_to_cover":             days_to_cover,       # ★
            "put_call_ratio":            put_call_ratio,
            "squeeze_risk_score":        squeeze_risk_score,  # ★
            # ★ Contrarian signal
            "sentiment_divergence":      sentiment_divergence, # ★
            # ★ Unusual options activity
            "unusual_call_activity":     unusual_call_activity, # ★
            "call_vol_to_oi":            call_vol_to_oi,        # ★
        }

        result = call_claude(
            SYSTEM_PROMPT,
            f"News/sentiment analysis for {ticker}: {json.dumps(market_data)}",
            "newshound",
        )
        # Append raw sentiment fields so the frontend can render the
        # "Noteworthy Considerations" section without a second API call.
        result.update({
            "news_sentiment_score":   market_data.get("news_sentiment_score"),
            "article_count_14d":      market_data.get("article_count_14d"),
            "consecutive_beats":      market_data.get("consecutive_beats"),
            "insider_mspr":           market_data.get("insider_mspr"),
            "squeeze_risk_score":     market_data.get("squeeze_risk_score"),
            "sentiment_divergence":   market_data.get("sentiment_divergence"),
            "unusual_call_activity":  market_data.get("unusual_call_activity"),
            "call_vol_to_oi":         market_data.get("call_vol_to_oi"),
            "short_interest_pct":     market_data.get("short_interest_pct"),
            "days_to_cover":          market_data.get("days_to_cover"),
            "analyst_upgrades_30d":   market_data.get("analyst_upgrades_30d"),
            "analyst_downgrades_30d": market_data.get("analyst_downgrades_30d"),
            "recent_headlines":       market_data.get("recent_headlines", [])[:5],
        })
        _cache[ticker] = {"ts": time.time(), "data": result}
        return result
    except Exception as e:
        return {
            "agent": "newshound", "ticker": ticker,
            "action": "HOLD", "confidence": 0.0,
            "rationale": f"Data fetch failed: {e}",
            "suggested_position_size_pct": 0,
        }
