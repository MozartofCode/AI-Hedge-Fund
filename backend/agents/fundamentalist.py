"""
Fundamentalist agent — FMP financial data + Claude analysis.
Round 3 additions: revenue acceleration, EPS acceleration, gross margin expansion YoY,
FCF inflection detection, R&D intensity, cash-to-debt ratio.
Round 4 additions: trust-weighted analyst consensus (winsorized), bootstrap CI,
DCF fair value from FMP, valuation signal (Strong Buy → Strong Sell).
"""
import json
import time
import numpy as np
from datetime import datetime
from backend.agents.base_agent import call_claude
from backend.data.fmp_client import (
    get_profile, get_income_statement, get_balance_sheet,
    get_cash_flow, get_analyst_ratings, get_earnings_calendar,
    get_analyst_price_target, get_analyst_price_targets, get_dcf,
)

# ── Institution trust weights (from valuation engine file) ───────────────────
# Higher = more track-record credibility. Used to weight individual price targets.
_TRUST = {
    "Goldman Sachs": 1.30, "Goldman": 1.30,
    "Bank of America": 1.25, "BofA": 1.25, "Merrill Lynch": 1.25,
    "Morgan Stanley": 1.20,
    "JPMorgan": 1.15, "J.P. Morgan": 1.15, "JP Morgan": 1.15,
    "Evercore": 1.10, "Evercore ISI": 1.10,
    "UBS": 1.10,
    "Barclays": 1.05,
    "Citigroup": 1.00, "Citi": 1.00,
    "Deutsche Bank": 0.95,
    "Wells Fargo": 0.90, "RBC": 0.90, "Royal Bank": 0.90,
    "Piper Sandler": 0.88, "Cowen": 0.88, "Jefferies": 0.88,
    "KeyBanc": 0.80, "Wedbush": 0.85, "Needham": 0.85,
}


def _winsorize(arr, lo=0.05, hi=0.95):
    a = np.array(arr, dtype=float)
    return np.clip(a, np.quantile(a, lo), np.quantile(a, hi))


def _bootstrap_wmean(vals, wts, n=1000, seed=42):
    rng = np.random.default_rng(seed)
    v, w = np.array(vals, dtype=float), np.array(wts, dtype=float)
    boots = []
    for _ in range(n):
        idx = rng.choice(len(v), size=len(v), replace=True)
        sw = w[idx]; sw = sw / sw.sum()
        boots.append(float(np.dot(v[idx], sw)))
    return float(np.mean(boots)), float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def _ws_consensus(indiv_targets: list, spot: float, consensus_fallback: dict) -> dict:
    """
    Trust-weighted, winsorized Wall Street analyst consensus with bootstrap CI.
    Mirrors the logic from the Fair Value Valuation Engine (file.py).
    """
    pts, wts = [], []
    for t in indiv_targets[:20]:
        pt = float(t.get("adjPriceTarget") or t.get("priceTarget") or 0)
        if pt <= 0:
            continue
        firm = t.get("analystCompany", "")
        tw = 1.0
        for k, v in _TRUST.items():
            if k.lower() in firm.lower():
                tw = v
                break
        pts.append(pt)
        wts.append(tw)

    if len(pts) < 3:
        # Fallback to FMP consensus when not enough individual targets
        cons = float(consensus_fallback.get("targetConsensus") or 0)
        hi   = float(consensus_fallback.get("targetHigh") or 0)
        lo   = float(consensus_fallback.get("targetLow") or 0)
        return {
            "ws_price":     round(cons, 2) if cons > 0 else None,
            "ws_price_high": round(hi, 2) if hi > 0 else None,
            "ws_price_low":  round(lo, 2) if lo > 0 else None,
            "ws_upside_pct": round((cons - spot) / spot * 100, 2) if spot > 0 and cons > 0 else None,
            "ws_ci_lo": None, "ws_ci_hi": None,
        }

    wins = _winsorize(pts)
    w_arr = np.array(wts); w_arr = w_arr / w_arr.sum()
    ws = float(np.dot(wins, w_arr))
    _, ci_lo, ci_hi = _bootstrap_wmean(wins, w_arr)

    return {
        "ws_price":      round(ws, 2),
        "ws_price_high": round(float(np.array(pts).max()), 2),
        "ws_price_low":  round(float(np.array(pts).min()), 2),
        "ws_upside_pct": round((ws - spot) / spot * 100, 2) if spot > 0 else None,
        "ws_ci_lo": round(ci_lo, 2),
        "ws_ci_hi": round(ci_hi, 2),
    }


def _valuation_signal(ws_price, spot, ci_lo=None, ci_hi=None, dcf_price=None) -> str:
    """
    Signal based on upside from spot + bootstrap confidence interval.
    Mirrors the signal() function from the Fair Value Valuation Engine.
    """
    # Use DCF as tiebreaker when WS not available
    fv = ws_price or dcf_price
    if not fv or not spot or spot <= 0:
        return "N/A"

    upside = (fv - spot) / spot * 100

    # Statistically strong: spot is outside the 95% CI
    if ci_lo is not None and spot < ci_lo:
        return "STRONG BUY"
    if ci_hi is not None and spot > ci_hi:
        return "STRONG SELL"

    if upside > 20:   return "STRONG BUY"
    if upside > 10:   return "BUY"
    if upside > 3:    return "OUTPERFORM"
    if upside < -20:  return "STRONG SELL"
    if upside < -10:  return "SELL"
    if upside < -3:   return "UNDERPERFORM"
    return "HOLD"

# 2-hour cache per ticker — FMP data changes at most once per quarter
_cache: dict = {}
_CACHE_TTL = 86400  # 24 hours — financials change quarterly, not intraday

SYSTEM_PROMPT = """You are the Fundamentalist on an AI investment committee hunting for 10X opportunities.
Return ONLY a valid JSON object — no markdown, no explanation, just JSON:
{
  "action": "BUY" | "SELL" | "HOLD",
  "confidence": 0.0-1.0,
  "rationale": "1 plain-English sentence — name the single most important financial signal (e.g. 'Revenue grew 45% last quarter and margins are expanding, making the valuation look reasonable.')",
  "suggested_position_size_pct": 0-12,
  "valuation_score": 0.0-1.0,
  "growth_score": 0.0-1.0,
  "profitability_score": 0.0-1.0
}

valuation_score: 1.0=extremely cheap (low P/E, PEG<1, P/FCF<15, big analyst upside), 0.0=extremely expensive (P/E>50, PEG>3, negative FCF). 0.5=fairly valued.
growth_score: 1.0=exceptional growth (YoY rev>30% AND accelerating, EPS accelerating, FCF inflection), 0.0=contracting revenue, negative EPS. 0.5=stable/slow.
profitability_score: 1.0=high margins expanding (gross>60%, op margin rising, growing FCF, low debt), 0.0=unprofitable (negative margins, cash burn, high leverage). 0.5=average.

PRIORITY SIGNALS for 10X identification (weight these above all others):

★ REVENUE ACCELERATION (rev_accel_yoy): The single best 10X predictor.
  - Positive = growth RATE is increasing QoQ. This is a re-rating catalyst.
  - rev_accel_yoy > +5pp = growth accelerating significantly = strong BUY signal
  - rev_accel_yoy < -5pp = growth decelerating = warning sign
  - Combined with rev_growth_yoy > 20%: company in hypergrowth = maximize score

★ EPS ACCELERATION (eps_accel_qoq): Earnings inflection = massive re-rating.
  - Positive and large = earnings growing faster each quarter = institution magnet
  - Three consecutive beats + accelerating EPS = near-certain multiple expansion

★ FCF INFLECTION (fcf_inflection=True): Company just turned cash-flow positive after burning cash.
  - This is a MAJOR inflection point. Market rarely prices this in fast enough.
  - FCF inflection = potential 2-3x re-rating over next 12 months

★ GROSS MARGIN EXPANSION (gross_margin_change_yoy > 200 bps): Pricing power / scale emerging.
  - Expanding margins at high revenue growth = competitive moat forming
  - This is what separates durable 10X from one-hit wonders

★ R&D INTENSITY (rd_intensity_pct): Tech/pharma with R&D > 15% of revenue = innovation pipeline.
  - High R&D + rising revenue + improving margins = reinvestment flywheel

★ RULE OF 40: For SaaS/software. Revenue growth % + FCF margin % > 40 = healthy. > 60 = elite.
  - Rule of 40 > 60 with positive trajectory = premium multiple justified

★ CASH-TO-DEBT (cash_to_debt): > 2.0 = war chest for growth. Debt-free (999) = maximum flexibility.

Standard signals:
- P/E: <15 cheap, >35 expensive (compare to sector). High P/E OK if growth is accelerating.
- PEG ratio: <1.0 = undervalued vs growth (strong buy). >2.0 = expensive vs growth.
- P/FCF: <20 healthy; >40 expensive; negative FCF = burning cash (OK early-stage if rev accelerating)
- Gross margin: >50% = pricing power; <20% = commodity
- Op margin trend: improving = efficiency gains
- Debt-to-equity: <1.0 conservative; >3.0 = high leverage risk
- Analyst target upside >25% = institutional conviction; <0% = analysts bearish
- Upcoming earnings within 3 days: increase caution (gap risk)

★ SHARE DILUTION (dilution_yoy_pct): Shares outstanding change year-over-year.
  - < -2% = buybacks shrinking float (very bullish — company confident, per-share value growing)
  - 0 to +5% = acceptable dilution (stock comp / small raises)
  - > +10% = heavy dilution destroying per-share value. Penalize significantly even if revenue grows.
  - Revenue growing 30% but shares +15% = only 13% per-share growth. Don't ignore this.

★ CURRENT RATIO (current_ratio): Current assets / current liabilities.
  - > 2.0 = strong liquidity buffer
  - 1.0–2.0 = adequate
  - < 1.0 = short-term cash stress — raise concern unless company has reliable revolving credit

★ BUYBACK YIELD (buyback_yield_pct): % of market cap repurchased last quarter (annualized).
  - > 3% = aggressive buybacks = strong capital allocation signal + float reduction
  - > 5% = exceptionally shareholder-friendly, supports per-share value

Prefer SELL with low confidence over HOLD when bearish. Reserve HOLD for genuine neutrality."""


def _get_fundamental_data(ticker: str) -> dict:
    """Fetch and cache all FMP data for a ticker. TTL = 24 hours."""
    if ticker in _cache:
        data, ts = _cache[ticker]
        if time.time() - ts < _CACHE_TTL:
            return data

    profile       = get_profile(ticker)
    income        = get_income_statement(ticker, limit=8)
    balance       = get_balance_sheet(ticker, limit=2)
    cash_flow     = get_cash_flow(ticker, limit=4)
    analyst       = get_analyst_ratings(ticker)
    earnings_cal  = get_earnings_calendar(ticker)
    price_target  = get_analyst_price_target(ticker)
    indiv_targets = get_analyst_price_targets(ticker, limit=20)   # for trust-weighted consensus
    dcf_data      = get_dcf(ticker)                               # FMP intrinsic value

    data = {
        "profile": profile, "income": income, "balance": balance,
        "cash_flow": cash_flow, "analyst": analyst,
        "earnings_cal": earnings_cal, "price_target": price_target,
        "indiv_targets": indiv_targets,
        "dcf_data": dcf_data,
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

        # ── Revenue growth YoY (same quarter last year) ───────────────────────
        rev_growth_yoy = None
        if len(income) >= 5:
            curr_yr = income[0].get("revenue") or 0
            prev_yr = income[4].get("revenue") or 1
            rev_growth_yoy = round((curr_yr - prev_yr) / abs(prev_yr) * 100, 2) if prev_yr else None

        # ── ★ Revenue ACCELERATION: delta of YoY growth rates ────────────────
        # Positive = growth rate itself is speeding up (key 10X signal)
        rev_accel_yoy = None
        if len(income) >= 6:
            try:
                r0 = income[0].get("revenue") or 0
                r1 = income[1].get("revenue") or 0
                r4 = income[4].get("revenue") or 0
                r5 = income[5].get("revenue") or 0
                if r4 and r5 and abs(r4) > 0 and abs(r5) > 0:
                    yoy_recent = (r0 - r4) / abs(r4) * 100
                    yoy_prior  = (r1 - r5) / abs(r5) * 100
                    rev_accel_yoy = round(yoy_recent - yoy_prior, 2)
            except Exception:
                pass

        # ── EPS growth QoQ ────────────────────────────────────────────────────
        eps_growth_qoq = None
        if len(income) >= 2:
            curr_eps = income[0].get("eps") or 0
            prev_eps = income[1].get("eps") or 0
            if prev_eps and prev_eps != 0:
                eps_growth_qoq = round((curr_eps - prev_eps) / abs(prev_eps) * 100, 2)

        # ── ★ EPS ACCELERATION: is earnings growth rate itself growing? ───────
        eps_accel_qoq = None
        if len(income) >= 4:
            try:
                e0 = income[0].get("eps") or 0
                e1 = income[1].get("eps") or 0
                e2 = income[2].get("eps") or 0
                if e1 and e1 != 0 and e2 and e2 != 0:
                    growth_q0 = (e0 - e1) / abs(e1) * 100
                    growth_q1 = (e1 - e2) / abs(e2) * 100
                    eps_accel_qoq = round(growth_q0 - growth_q1, 2)
            except Exception:
                pass

        # ── Debt-to-equity ────────────────────────────────────────────────────
        dte = None
        if balance:
            debt   = balance[0].get("totalDebt") or 0
            equity = balance[0].get("totalStockholdersEquity") or 1
            dte    = round(debt / equity, 2) if equity else None

        # ── FCF trend ─────────────────────────────────────────────────────────
        fcf = [cf.get("freeCashFlow") for cf in cash_flow if cf.get("freeCashFlow") is not None]

        # ── ★ FCF INFLECTION: was negative, now positive ──────────────────────
        fcf_inflection = False
        try:
            if len(fcf) >= 3:
                recent_positive = (fcf[0] or 0) > 0
                was_negative    = any((f or 0) < 0 for f in fcf[1:4])
                fcf_inflection  = recent_positive and was_negative
        except Exception:
            pass

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

        # ── ★ Gross margin expansion YoY (> 200 bps = pricing power forming) ─
        gross_margin_change_yoy = None
        try:
            if len(income) >= 5:
                rev0  = float(income[0].get("revenue") or 0)
                cogs0 = float(income[0].get("costOfRevenue") or 0)
                rev4  = float(income[4].get("revenue") or 0)
                cogs4 = float(income[4].get("costOfRevenue") or 0)
                if rev0 > 0 and rev4 > 0:
                    gm0 = (rev0 - cogs0) / rev0 * 100
                    gm4 = (rev4 - cogs4) / rev4 * 100
                    gross_margin_change_yoy = round(gm0 - gm4, 2)
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

        # ── ★ R&D intensity (% of revenue) ────────────────────────────────────
        rd_intensity_pct = None
        try:
            if income:
                rd  = float(income[0].get("researchAndDevelopmentExpenses") or 0)
                rev = float(income[0].get("revenue") or 0)
                if rev > 0 and rd > 0:
                    rd_intensity_pct = round(rd / rev * 100, 2)
        except Exception:
            pass

        # ── ★ Cash-to-debt ratio ───────────────────────────────────────────────
        cash_to_debt = None
        try:
            if balance:
                cash_pos = (
                    float(balance[0].get("cashAndCashEquivalents") or 0)
                    + float(balance[0].get("shortTermInvestments") or 0)
                )
                debt_pos = float(balance[0].get("totalDebt") or 0)
                if debt_pos > 0:
                    cash_to_debt = round(cash_pos / debt_pos, 2)
                elif cash_pos > 0:
                    cash_to_debt = 999  # debt-free
        except Exception:
            pass

        # ── ★ Rule of 40 (for SaaS/software) ──────────────────────────────────
        rule_of_40 = None
        try:
            if rev_growth_yoy is not None and fcf and fcf[0] and income:
                rev_latest = float(income[0].get("revenue") or 0)
                if rev_latest > 0:
                    fcf_margin = fcf[0] / rev_latest * 100
                    rule_of_40 = round(rev_growth_yoy + fcf_margin, 1)
        except Exception:
            pass

        # ── ★ Share dilution YoY ─────────────────────────────────────────────
        # Positive = shares outstanding growing (dilutive, bad for per-share value)
        # Negative = buybacks shrinking share count (bullish)
        dilution_yoy_pct = None
        try:
            if len(income) >= 5:
                sh_now  = (income[0].get("weightedAverageShsDilOut")
                           or income[0].get("weightedAverageShsOut") or 0)
                sh_year = (income[4].get("weightedAverageShsDilOut")
                           or income[4].get("weightedAverageShsOut") or 0)
                if sh_year and sh_year > 0:
                    dilution_yoy_pct = round((sh_now - sh_year) / sh_year * 100, 2)
        except Exception:
            pass

        # ── ★ Current ratio (liquidity check) ────────────────────────────────
        current_ratio = None
        try:
            if balance:
                curr_assets = float(balance[0].get("totalCurrentAssets") or 0)
                curr_liab   = float(balance[0].get("totalCurrentLiabilities") or 0)
                if curr_liab > 0:
                    current_ratio = round(curr_assets / curr_liab, 2)
        except Exception:
            pass

        # ── ★ Buyback yield ───────────────────────────────────────────────────
        buyback_yield_pct = None
        try:
            if cash_flow and profile:
                repurchased = abs(float(cash_flow[0].get("commonStockRepurchased") or 0))
                mkt_cap     = float(profile.get("mktCap") or 0)
                if mkt_cap > 0 and repurchased > 0:
                    buyback_yield_pct = round(repurchased / mkt_cap * 100, 2)
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
            "ticker":                    ticker,
            "sector":                    profile.get("sector"),
            # Valuation
            "pe_ratio":                  profile.get("pe"),
            "peg_ratio":                 peg_ratio,
            "price_to_fcf":              pfcf,
            "analyst_target_upside_pct": target_upside_pct,
            # ★ Growth inflection signals
            "revenue_growth_qoq_pct":    rev_growth_qoq,
            "revenue_growth_yoy_pct":    rev_growth_yoy,
            "rev_accel_yoy":             rev_accel_yoy,
            "eps_growth_qoq_pct":        eps_growth_qoq,
            "eps_accel_qoq":             eps_accel_qoq,
            "fcf_inflection":            fcf_inflection,
            # ★ Margin quality signals
            "gross_margin_pct":          gross_margin_pct,
            "gross_margin_change_yoy":   gross_margin_change_yoy,
            "operating_margin_pct":      op_margin_pct,
            "operating_margin_trend":    op_margin_trend,
            # ★ Balance sheet / efficiency
            "rd_intensity_pct":          rd_intensity_pct,
            "cash_to_debt":              cash_to_debt,
            "rule_of_40":                rule_of_40,
            "debt_to_equity":            dte,
            # FCF
            "free_cash_flow_trend":      fcf[:4],
            # Analyst consensus
            "analyst_buy":               analyst.get("analystRatingsBuy"),
            "analyst_hold":              analyst.get("analystRatingsHold"),
            "analyst_sell":              analyst.get("analystRatingsSell"),
            # Market context
            "market_cap":                profile.get("mktCap"),
            "upcoming_earnings":         upcoming_earnings,
            # ★ New signals
            "dilution_yoy_pct":          dilution_yoy_pct,
            "current_ratio":             current_ratio,
            "buyback_yield_pct":         buyback_yield_pct,
        }

        result = call_claude(
            SYSTEM_PROMPT,
            f"Fundamental analysis for {ticker}: {json.dumps(market_data)}",
            "fundamentalist",
        )

        # ── Valuation engine (from Fair Value Valuation Engine) ───────────────
        spot_price   = float(profile.get("price") or 0)
        company_name = profile.get("companyName") or ticker

        # FMP DCF intrinsic value
        dcf_price = None
        try:
            dcf_raw = d["dcf_data"].get("dcf")
            if dcf_raw:
                dcf_price = round(float(dcf_raw), 2)
        except Exception:
            pass

        # Trust-weighted + winsorized Wall Street consensus
        ws_data = _ws_consensus(d["indiv_targets"], spot_price, d["price_target"])

        # Valuation signal (Strong Buy → Strong Sell)
        signal = _valuation_signal(
            ws_data.get("ws_price"), spot_price,
            ws_data.get("ws_ci_lo"), ws_data.get("ws_ci_hi"),
            dcf_price,
        )

        # Append all valuation + section data to the Claude result
        result.update({
            "company_name":     company_name,
            "spot_price":       round(spot_price, 2) if spot_price else None,
            "dcf_price":        dcf_price,
            **ws_data,
            "valuation_signal": signal,
            # ── Section data for frontend display ─────────────────────────────
            "valuation_section": {
                "pe_ratio":       market_data["pe_ratio"],
                "peg_ratio":      market_data["peg_ratio"],
                "p_fcf":          market_data["price_to_fcf"],
                "rev_growth_yoy": market_data["revenue_growth_yoy_pct"],
                "rev_accel":      market_data["rev_accel_yoy"],
                "eps_accel":      market_data["eps_accel_qoq"],
                "fcf_inflection": market_data["fcf_inflection"],
                "rule_of_40":     market_data["rule_of_40"],
                "analyst_upside": market_data["analyst_target_upside_pct"],
            },
            "financial_section": {
                "gross_margin":        market_data["gross_margin_pct"],
                "gross_margin_change": market_data["gross_margin_change_yoy"],
                "op_margin":           market_data["operating_margin_pct"],
                "op_margin_trend":     market_data["operating_margin_trend"],
                "debt_to_equity":      market_data["debt_to_equity"],
                "current_ratio":       market_data["current_ratio"],
                "cash_to_debt":        market_data["cash_to_debt"],
                "buyback_yield":       market_data["buyback_yield_pct"],
                "dilution_yoy":        market_data["dilution_yoy_pct"],
                "rd_intensity":        market_data["rd_intensity_pct"],
            },
        })
        return result

    except Exception as e:
        import traceback
        print(f"[fundamentalist] {ticker} FAILED: {e}\n{traceback.format_exc()}")
        return {
            "agent": "fundamentalist", "ticker": ticker,
            "action": "HOLD", "confidence": 0.0,
            "rationale": f"Data fetch failed: {e}",
            "suggested_position_size_pct": 0,
        }
