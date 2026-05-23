import json
from datetime import datetime
from backend.agents.base_agent import call_claude
from backend.data.fmp_client import (
    get_profile, get_income_statement, get_balance_sheet,
    get_cash_flow, get_analyst_ratings, get_earnings_calendar,
)

SYSTEM_PROMPT = """You are the Fundamentalist on an AI trading committee. Analyze company health, valuation, and earnings.
Return ONLY a valid JSON object — no markdown, no explanation, just JSON:
{
  "action": "BUY" | "SELL" | "HOLD",
  "confidence": 0.0-1.0,
  "rationale": "2-3 sentences citing specific financial metrics",
  "suggested_position_size_pct": 0-10
}
Key signals and thresholds:
- P/E ratio: <15 cheap, >35 expensive (sector-dependent)
- P/FCF ratio: <20 healthy; >40 expensive; negative FCF = concern
- Gross margin: >50% = pricing power / moat (tech/pharma); <20% = commodity business
- Revenue growth QoQ/YoY: >10% = growth, <0% = contraction
- Free cash flow trend: consistently positive and growing = quality business
- Debt-to-equity: <1.0 conservative; >3.0 high leverage (risky in rising rate env.)
- Analyst consensus: heavy buy-side = momentum; heavy sell-side = caution
- Upcoming earnings within 2 days: avoid new positions unless thesis is exceptionally strong"""


def get_vote(ticker: str) -> dict:
    try:
        profile      = get_profile(ticker)
        income       = get_income_statement(ticker, limit=4)
        balance      = get_balance_sheet(ticker, limit=2)
        cash_flow    = get_cash_flow(ticker, limit=4)
        analyst      = get_analyst_ratings(ticker)
        earnings_cal = get_earnings_calendar(ticker)

        # Revenue growth QoQ
        rev_growth = None
        if len(income) >= 2:
            curr = income[0].get("revenue") or 0
            prev = income[1].get("revenue") or 1
            rev_growth = round((curr - prev) / abs(prev) * 100, 2) if prev else None

        # Debt-to-equity
        dte = None
        if balance:
            debt   = balance[0].get("totalDebt") or 0
            equity = balance[0].get("totalStockholdersEquity") or 1
            dte    = round(debt / equity, 2) if equity else None

        # FCF trend (last 4 quarters)
        fcf = [cf.get("freeCashFlow") for cf in cash_flow if cf.get("freeCashFlow") is not None]

        # Price-to-Free-Cash-Flow
        pfcf = None
        try:
            price  = float(profile.get("price") or 0)
            shares = float(profile.get("sharesOutstanding") or 0)
            latest_fcf = fcf[0] if fcf else None
            if price > 0 and shares > 0 and latest_fcf and latest_fcf > 0:
                market_cap = price * shares
                pfcf = round(market_cap / latest_fcf, 2)
        except Exception:
            pass

        # Gross margin (revenue - COGS) / revenue
        gross_margin_pct = None
        try:
            if income:
                rev  = float(income[0].get("revenue") or 0)
                cogs = float(income[0].get("costOfRevenue") or 0)
                if rev > 0:
                    gross_margin_pct = round((rev - cogs) / rev * 100, 2)
        except Exception:
            pass

        # Days until next earnings
        upcoming_earnings = None
        today = datetime.now().date()
        for e in earnings_cal:
            try:
                edate = datetime.strptime(e.get("date", ""), "%Y-%m-%d").date()
                days  = (edate - today).days
                if 0 <= days <= 14:
                    upcoming_earnings = {"date": str(edate), "days_until": days}
                    break
            except Exception:
                pass

        market_data = {
            "ticker":               ticker,
            "pe_ratio":             profile.get("pe"),
            "price_to_fcf":         pfcf,
            "gross_margin_pct":     gross_margin_pct,
            "sector":               profile.get("sector"),
            "market_cap":           profile.get("mktCap"),
            "revenue_growth_pct":   rev_growth,
            "debt_to_equity":       dte,
            "free_cash_flow_trend": fcf[:4],
            "analyst_buy":          analyst.get("analystRatingsBuy"),
            "analyst_hold":         analyst.get("analystRatingsHold"),
            "analyst_sell":         analyst.get("analystRatingsSell"),
            "upcoming_earnings":    upcoming_earnings,
        }

        return call_claude(
            SYSTEM_PROMPT,
            f"Fundamental analysis for {ticker}: {json.dumps(market_data)}",
            "fundamentalist",
        )
    except Exception as e:
        return {
            "agent": "fundamentalist", "ticker": ticker,
            "action": "HOLD", "confidence": 0.0,
            "rationale": f"Data fetch failed: {e}",
            "suggested_position_size_pct": 0,
        }
