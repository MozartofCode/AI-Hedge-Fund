import json
import time
from datetime import datetime
from backend.agents.base_agent import call_claude
from backend.data.fmp_client import (
    get_profile, get_income_statement, get_balance_sheet,
    get_cash_flow, get_analyst_ratings, get_earnings_calendar,
    get_analyst_price_target,
)

# 2-hour cache per ticker — FMP data changes at most once per quarter
_cache: dict = {}
_CACHE_TTL = 7200  # seconds

SYSTEM_PROMPT = """You are the Fundamentalist on an AI trading committee. Analyze company health, valuation, and earnings.
Return ONLY a valid JSON object — no markdown, no explanation, just JSON:
{
  "action": "BUY" | "SELL" | "HOLD",
  "confidence": 0.0-1.0,
  "rationale": "2-3 sentences citing specific financial metrics",
  "suggested_position_size_pct": 0-10
}

Key signals and thresholds:
- P/E ratio: <15 cheap, >35 expensive (always compare to sector)
- P/FCF ratio: <20 healthy; >40 expensive; negative FCF = red flag
- PEG ratio: <1.0 = undervalued vs growth rate (strong buy signal); >2.0 = overvalued vs growth
- Gross margin: >50% = pricing power / moat (tech/pharma); <20% = commodity business
- Operating margin: improving QoQ = efficiency gains (bullish); deteriorating = cost pressure (bearish)
- Revenue growth YoY (preferred over QoQ — removes seasonality): >15% = strong growth; <0% = contraction
- EPS growth QoQ: accelerating earnings = high confidence BUY signal
- Free cash flow: consistently positive and growing = quality business; negative = burning cash
- Debt-to-equity: <1.0 = conservative; >3.0 = high leverage
- Analyst price target upside: >25% above current = strong institutional conviction; <0% = analysts bearish
- Analyst consensus: more buys = momentum; more sells = concern
- Upcoming earnings within 3 days: avoid new positions (gap risk)

Prefer SELL with low confidence over HOLD when bearish. Reserve HOLD for genuine neutrality."""


def _get_fundamental_data(ticker: str) -> dict:
    """Fetch and cache all FMP data for a ticker. TTL = 2 hours."""
    if ticker in _cache:
        data, ts = _cache[ticker]
        if time.time() - ts < _CACHE_TTL:
            return data

    profile      = get_profile(ticker)
    income       = get_income_statement(ticker, limit=8)   # 8 quarters for YoY
    balance      = get_balance_sheet(ticker, limit=2)
    cash_flow    = get_cash_flow(ticker, limit=4)
    analyst      = get_analyst_ratings(ticker)
    earnings_cal = get_earnings_calendar(ticker)
    price_target = get_analyst_price_target(ticker)

    data = {
        "profile": profile, "income": income, "balance": balance,
        "cash_flow": cash_flow, "analyst": analyst,
        "earnings_cal": earnings_cal, "price_target": price_target,
    }
    _cache[ticker] = (data, time.time())
    return data


def get_vote(ticker: str) -> dict:
    try:
        d = _get_fundamental_data(ticker)
        profile, income, balance = d["profile"], d["income"], d["balance"]
        cash_flow, analyst       = d["cash_flow"], d["analyst"]
        earnings_cal             = d["earnings_cal"]
        price_target             = d["price_target"]

        # ── Revenue growth QoQ ────────────────────────────────────────────────
        rev_growth_qoq = None
        if len(income) >= 2:
            curr = income[0].get("revenue") or 0
            prev = income[1].get("revenue") or 1
            rev_growth_qoq = round((curr - prev) / abs(prev) * 100, 2) if prev else None

        # ── Revenue growth YoY (same quarter last year — removes seasonality) ─
        rev_growth_yoy = None
        if len(income) >= 5:
            curr_yr = income[0].get("revenue") or 0
            prev_yr = income[4].get("revenue") or 1
            rev_growth_yoy = round((curr_yr - prev_yr) / abs(prev_yr) * 100, 2) if prev_yr else None

        # ── EPS growth QoQ ────────────────────────────────────────────────────
        eps_growth_qoq = None
        if len(income) >= 2:
            curr_eps = income[0].get("eps") or 0
            prev_eps = income[1].get("eps") or 0
            if prev_eps and prev_eps != 0:
                eps_growth_qoq = round((curr_eps - prev_eps) / abs(prev_eps) * 100, 2)

        # ── Debt-to-equity ────────────────────────────────────────────────────
        dte = None
        if balance:
            debt   = balance[0].get("totalDebt") or 0
            equity = balance[0].get("totalStockholdersEquity") or 1
            dte    = round(debt / equity, 2) if equity else None

        # ── FCF trend ─────────────────────────────────────────────────────────
        fcf = [cf.get("freeCashFlow") for cf in cash_flow if cf.get("freeCashFlow") is not None]

        # ── Price-to-Free-Cash-Flow ───────────────────────────────────────────
        pfcf = None
        try:
            price  = float(profile.get("price") or 0)
            shares = float(profile.get("sharesOutstanding") or 0)
            if price > 0 and shares > 0 and fcf and fcf[0] and fcf[0] > 0:
                pfcf = round(price * shares / fcf[0], 2)
        except Exception:
            pass

        # ── Gross margin ──────────────────────────────────────────────────────
        gross_margin_pct = None
        try:
            if income:
                rev  = float(income[0].get("revenue") or 0)
                cogs = float(income[0].get("costOfRevenue") or 0)
                if rev > 0:
                    gross_margin_pct = round((rev - cogs) / rev * 100, 2)
        except Exception:
            pass

        # ── Operating margin ──────────────────────────────────────────────────
        op_margin_pct = None
        op_margin_prev_pct = None
        try:
            if income:
                rev    = float(income[0].get("revenue") or 0)
                op_inc = float(income[0].get("operatingIncome") or 0)
                if rev > 0:
                    op_margin_pct = round(op_inc / rev * 100, 2)
            if len(income) >= 2:
                rev2    = float(income[1].get("revenue") or 0)
                op_inc2 = float(income[1].get("operatingIncome") or 0)
                if rev2 > 0:
                    op_margin_prev_pct = round(op_inc2 / rev2 * 100, 2)
        except Exception:
            pass

        op_margin_trend = None
        if op_margin_pct is not None and op_margin_prev_pct is not None:
            op_margin_trend = round(op_margin_pct - op_margin_prev_pct, 2)

        # ── PEG ratio ─────────────────────────────────────────────────────────
        peg_ratio = None
        try:
            pe = profile.get("pe")
            if pe and eps_growth_qoq and eps_growth_qoq > 0:
                eps_growth_annual = eps_growth_qoq * 4
                if eps_growth_annual > 0:
                    peg_ratio = round(float(pe) / eps_growth_annual, 2)
        except Exception:
            pass

        # ── Analyst price target upside ───────────────────────────────────────
        target_upside_pct = None
        try:
            target = price_target.get("targetConsensus") or price_target.get("targetMedian")
            cur    = profile.get("price")
            if target and cur and float(cur) > 0:
                target_upside_pct = round((float(target) - float(cur)) / float(cur) * 100, 2)
        except Exception:
            pass

        # ── Upcoming earnings ─────────────────────────────────────────────────
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
            "ticker":                   ticker,
            "sector":                   profile.get("sector"),
            "pe_ratio":                 profile.get("pe"),
            "peg_ratio":                peg_ratio,
            "price_to_fcf":             pfcf,
            "gross_margin_pct":         gross_margin_pct,
            "operating_margin_pct":     op_margin_pct,
            "operating_margin_trend":   op_margin_trend,
            "market_cap":               profile.get("mktCap"),
            "revenue_growth_qoq_pct":   rev_growth_qoq,
            "revenue_growth_yoy_pct":   rev_growth_yoy,
            "eps_growth_qoq_pct":       eps_growth_qoq,
            "debt_to_equity":           dte,
            "free_cash_flow_trend":     fcf[:4],
            "analyst_buy":              analyst.get("analystRatingsBuy"),
            "analyst_hold":             analyst.get("analystRatingsHold"),
            "analyst_sell":             analyst.get("analystRatingsSell"),
            "analyst_target_upside_pct": target_upside_pct,
            "upcoming_earnings":        upcoming_earnings,
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
