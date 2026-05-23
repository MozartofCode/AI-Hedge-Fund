import asyncio
import json
from datetime import datetime

from backend.agents.base_agent import call_claude
from backend.agents import technician, fundamentalist, newshound, macro_watcher, risk_manager
from backend.broker.paper_broker import get_portfolio, is_market_open, place_order
from backend.db.session import AsyncSessionLocal
from backend.db.crud import (
    create_session, save_agent_vote, finalize_session,
    log_trade, save_portfolio_snapshot, get_peak_portfolio_value,
)
from backend.notifications.slack_notifier import notify_trade

# ── 25-ticker watchlist: mega-caps + high-growth 10X candidates ───────────────
WATCHLIST = [
    # Mega-cap tech & AI
    "AAPL", "NVDA", "MSFT", "GOOGL",
    # AI infrastructure & semis
    "AMD", "ARM", "AVGO", "SMCI",
    # Cloud / cybersecurity / software (real 10X candidates)
    "META", "PLTR", "CRWD", "NET", "DDOG",
    # Consumer & EV
    "AMZN", "TSLA",
    # Financials & fintech (includes crypto proxy)
    "JPM", "GS", "HOOD", "SOFI", "MSTR",
    # Healthcare
    "UNH", "LLY",
    # Energy
    "XOM",
    # Market ETFs (broad regime signals)
    "SPY", "QQQ",
]

# ── Base agent weights (regime-adjusted in _get_weights) ─────────────────────
_BASE_WEIGHTS = {
    "technician":     0.30,
    "fundamentalist": 0.25,
    "newshound":      0.20,
    "macro_watcher":  0.25,
}

# ── Decision thresholds ───────────────────────────────────────────────────────
BUY_THRESHOLD  = 0.60
SELL_THRESHOLD = 0.35

# ── Conviction-based position sizing ─────────────────────────────────────────
_BASE_POSITION_PCT = 5.0
_MAX_POSITION_PCT  = 12.0   # raised to 12% for highest-conviction plays

CHAIRMAN_SYSTEM = """You are the Chairman of an AI investment committee hunting for asymmetric returns and 10X opportunities.
You have received analysis from 5 specialized agents covering technicals, fundamentals, news, macro, and risk.

Your mandate: FIND AND BET BIG ON HIGH-CONVICTION OPPORTUNITIES. Don't manage a bond portfolio — this is growth capital.

Decision framework:
- Strong BUY signals (score >0.80 with inflection evidence) → BUY with larger size (8-12%). Don't be timid.
- Revenue acceleration + margin expansion + Stage 2 uptrend = highest-priority BUY setup.
- If FCF turned positive recently or EPS is accelerating, that is a major inflection — act on it.
- Squeeze risk (high short interest + positive catalyst) = explosive move potential.
- Take-profit at +75% is a safety ceiling — for confirmed growth compounders in Stage 2, consider HOLD.
- Respect the Risk Manager's stop-loss and veto rules — protect capital.
- SELL committee votes from multiple agents should be respected promptly.

Return ONLY a valid JSON object — no markdown, no explanation, just JSON:
{
  "decision": "BUY" | "SELL" | "HOLD",
  "ticker": "...",
  "position_size_pct": 0-12,
  "order_type": "market",
  "chairman_rationale": "3-4 sentences: what is the core thesis, what inflection/signal is being acted on, what could go wrong, and why the sizing is appropriate"
}"""


def _get_weights(risk_off: bool, vix: float = None, spy_above_200d: bool = None) -> dict:
    """
    Dynamically shift agent weights based on market regime.
    In crisis/bear markets, macro and news signals matter most.
    In bull markets, momentum (technician) and quality (fundamentalist) lead.
    """
    if risk_off or (vix is not None and vix > 25):
        # High-vol / crisis: macro and news dominate
        return {"technician": 0.15, "fundamentalist": 0.15, "newshound": 0.30, "macro_watcher": 0.40}
    elif spy_above_200d is False:
        # Bear market: reduce momentum, increase fundamentals and macro
        return {"technician": 0.20, "fundamentalist": 0.30, "newshound": 0.20, "macro_watcher": 0.30}
    else:
        # Bull / neutral: slight momentum bias
        return _BASE_WEIGHTS


def _action_score(action: str, confidence: float) -> float:
    """
    Map an agent's action + confidence to a 0–1 bullish score.
    BUY confidence 1.0 = fully bullish (1.0).
    SELL confidence 1.0 = fully bearish (0.0).
    HOLD = genuinely neutral (0.5) regardless of confidence — agents are
    instructed to use SELL/BUY with low confidence rather than HOLD when biased.
    """
    if action == "BUY":
        return confidence
    if action == "SELL":
        return 1.0 - confidence
    return 0.5


def _weighted_score(votes: list, weights: dict) -> float:
    total_w = sum(weights.values())
    raw = sum(
        weights.get(v.get("agent"), 0) * _action_score(v.get("action", "HOLD"), float(v.get("confidence", 0.5)))
        for v in votes
        if v.get("agent") in weights
    )
    return round(raw / total_w, 4) if total_w > 0 else 0.5


def _conviction_position_size(score: float) -> float:
    """Scale position size with conviction: 5% at threshold → 10% at perfect score."""
    conviction = (score - BUY_THRESHOLD) / (1.0 - BUY_THRESHOLD)
    size = _BASE_POSITION_PCT + conviction * (_MAX_POSITION_PCT - _BASE_POSITION_PCT)
    return round(min(_MAX_POSITION_PCT, max(_BASE_POSITION_PCT, size)), 1)


async def run_committee_for_ticker(ticker: str, portfolio: dict, peak_value: float) -> dict:
    # Run 4 data agents in parallel
    tech_vote, fund_vote, news_vote, macro_vote = await asyncio.gather(
        asyncio.to_thread(technician.get_vote, ticker),
        asyncio.to_thread(fundamentalist.get_vote, ticker),
        asyncio.to_thread(newshound.get_vote, ticker),
        asyncio.to_thread(macro_watcher.get_vote, ticker),
    )

    agent_votes = [tech_vote, fund_vote, news_vote, macro_vote]
    risk_vote   = risk_manager.get_vote(ticker, portfolio=portfolio, peak_value=peak_value)

    # ── Regime-aware weights ─────────────────────────────────────────────────
    risk_off       = macro_vote.get("risk_off", False)
    vix_raw        = macro_vote.get("vix_raw")
    spy_above_200d = macro_vote.get("spy_above_200d")
    weights        = _get_weights(risk_off, vix_raw, spy_above_200d)
    score          = _weighted_score(agent_votes, weights)

    # ── Decision logic (stop-loss / profit-target override first) ────────────
    force_sell   = risk_vote.get("force_sell", False)
    take_profit  = risk_vote.get("take_profit", False)
    holds_ticker = any(p["ticker"] == ticker for p in portfolio.get("positions", []))

    if force_sell or take_profit:
        decision      = "SELL"
        position_size = _BASE_POSITION_PCT
    elif risk_vote.get("veto"):
        decision      = "HOLD"
        position_size = 0.0
    elif score >= BUY_THRESHOLD:
        decision      = "BUY"
        position_size = _conviction_position_size(score)
    elif score <= SELL_THRESHOLD and holds_ticker:
        decision      = "SELL"
        position_size = _BASE_POSITION_PCT
    else:
        decision      = "HOLD"
        position_size = 0.0

    # ── Chairman rationale via Claude ─────────────────────────────────────────
    chairman_input = {
        "ticker":             ticker,
        "weighted_score":     score,
        "risk_off":           risk_off,
        "spy_above_200d":     spy_above_200d,
        "active_weights":     weights,
        "risk_manager_veto":  risk_vote.get("veto"),
        "force_sell":         force_sell,
        "take_profit":        take_profit,
        "risk_manager_reason": risk_vote.get("reason"),
        "preliminary_decision": decision,
        "portfolio_context": {
            "cash_available": round(portfolio.get("cash", 0), 2),
            "total_value":    round(portfolio.get("total_value", 0), 2),
            "open_positions": [p["ticker"] for p in portfolio.get("positions", [])],
            "num_positions":  len(portfolio.get("positions", [])),
        },
        "agent_votes": [
            {"agent": v.get("agent"), "action": v.get("action"),
             "confidence": v.get("confidence"), "rationale": v.get("rationale")}
            for v in agent_votes
        ],
    }
    chairman_out = call_claude(
        CHAIRMAN_SYSTEM,
        f"Committee analysis: {json.dumps(chairman_input)}",
        "chairman",
        max_tokens=800,
    )

    final_decision = chairman_out.get("decision", decision)
    # Hard-enforce risk manager rules
    if risk_vote.get("veto") and final_decision == "BUY":
        final_decision = "HOLD"
    if (force_sell or take_profit) and final_decision != "SELL":
        final_decision = "SELL"

    try:
        final_size = float(chairman_out.get("position_size_pct", position_size))
    except (TypeError, ValueError):
        final_size = position_size

    rationale = chairman_out.get("chairman_rationale", "No rationale provided.")

    # ── Persist to DB ─────────────────────────────────────────────────────────
    async with AsyncSessionLocal() as db:
        session = await create_session(db, ticker)

        for vote in agent_votes:
            await save_agent_vote(db, session.id, {
                "agent":      vote.get("agent", "unknown"),
                "action":     vote.get("action", "HOLD"),
                "confidence": vote.get("confidence", 0.0),
                "rationale":  vote.get("rationale", ""),
                "raw_data":   vote,
            })
        await save_agent_vote(db, session.id, {
            "agent":      "risk_manager",
            "action":     "SELL" if (force_sell or take_profit) else "HOLD",
            "confidence": 0.0,
            "rationale":  risk_vote.get("reason", ""),
            "raw_data":   risk_vote,
        })

        order_placed = False
        order_id     = None
        if is_market_open() and final_decision in ("BUY", "SELL") and final_size > 0:
            try:
                order        = await place_order(ticker, final_decision.lower(), final_size)
                order_placed = True
                order_id     = order.get("order_id")
                await log_trade(db, session.id, {
                    "ticker":       ticker,
                    "side":         final_decision.lower(),
                    "qty":          order.get("qty"),
                    "filled_price": order.get("price"),
                    "filled_at":    datetime.utcnow(),
                    "order_id":     order_id,
                })
                _votes_for_slack = [
                    {"agent_name": v.get("agent"), "action": v.get("action", "HOLD"),
                     "confidence": v.get("confidence", 0.0), "veto": False}
                    for v in agent_votes
                ] + [{
                    "agent_name": "risk_manager", "action": "HOLD",
                    "confidence": 0.0, "veto": risk_vote.get("veto", False),
                }]
                await notify_trade(
                    ticker=ticker, side=final_decision.lower(),
                    qty=order.get("qty", 0), price=order.get("price", 0.0),
                    chairman_rationale=rationale, agent_votes=_votes_for_slack,
                    weighted_score=score,
                )
            except Exception as e:
                rationale += f" [Order failed: {e}]"

        await finalize_session(db, session.id, {
            "decision":           final_decision,
            "chairman_rationale": rationale,
            "weighted_score":     score,
            "order_placed":       order_placed,
            "order_id":           order_id,
        })

    return {
        "ticker":              ticker,
        "decision":            final_decision,
        "weighted_score":      score,
        "chairman_rationale":  rationale,
        "order_placed":        order_placed,
        "risk_off":            risk_off,
        "risk_manager_veto":   risk_vote.get("veto"),
        "force_sell":          force_sell,
        "take_profit":         take_profit,
    }


async def analyze_ticker(ticker: str) -> dict:
    """
    Run all 5 agents + Chairman for a single ticker.
    Analysis-only — no order placed, works when market is closed.
    """
    portfolio = await get_portfolio()
    async with AsyncSessionLocal() as db:
        peak_value = await get_peak_portfolio_value(db)

    tech_vote, fund_vote, news_vote, macro_vote = await asyncio.gather(
        asyncio.to_thread(technician.get_vote, ticker),
        asyncio.to_thread(fundamentalist.get_vote, ticker),
        asyncio.to_thread(newshound.get_vote, ticker),
        asyncio.to_thread(macro_watcher.get_vote, ticker),
    )

    agent_votes    = [tech_vote, fund_vote, news_vote, macro_vote]
    risk_vote      = risk_manager.get_vote(ticker, portfolio=portfolio, peak_value=peak_value)
    risk_off       = macro_vote.get("risk_off", False)
    vix_raw        = macro_vote.get("vix_raw")
    spy_above_200d = macro_vote.get("spy_above_200d")
    weights        = _get_weights(risk_off, vix_raw, spy_above_200d)
    score          = _weighted_score(agent_votes, weights)

    force_sell  = risk_vote.get("force_sell", False)
    take_profit = risk_vote.get("take_profit", False)
    holds_ticker = any(p["ticker"] == ticker for p in portfolio.get("positions", []))

    if force_sell or take_profit:
        decision      = "SELL"
        position_size = _BASE_POSITION_PCT
    elif risk_vote.get("veto"):
        decision      = "HOLD"
        position_size = 0.0
    elif score >= BUY_THRESHOLD:
        decision      = "BUY"
        position_size = _conviction_position_size(score)
    elif score <= SELL_THRESHOLD and holds_ticker:
        decision      = "SELL"
        position_size = _BASE_POSITION_PCT
    else:
        decision      = "HOLD"
        position_size = 0.0

    chairman_input = {
        "ticker":              ticker,
        "weighted_score":      score,
        "risk_off":            risk_off,
        "spy_above_200d":      spy_above_200d,
        "active_weights":      weights,
        "risk_manager_veto":   risk_vote.get("veto"),
        "force_sell":          force_sell,
        "take_profit":         take_profit,
        "risk_manager_reason": risk_vote.get("reason"),
        "preliminary_decision": decision,
        "portfolio_context": {
            "cash_available": round(portfolio.get("cash", 0), 2),
            "total_value":    round(portfolio.get("total_value", 0), 2),
            "open_positions": [p["ticker"] for p in portfolio.get("positions", [])],
            "num_positions":  len(portfolio.get("positions", [])),
        },
        "agent_votes": [
            {"agent": v.get("agent"), "action": v.get("action"),
             "confidence": v.get("confidence"), "rationale": v.get("rationale")}
            for v in agent_votes
        ],
    }
    chairman_out = call_claude(
        CHAIRMAN_SYSTEM,
        f"Committee analysis: {json.dumps(chairman_input)}",
        "chairman",
        max_tokens=800,
    )

    final_decision = chairman_out.get("decision", decision)
    if risk_vote.get("veto") and final_decision == "BUY":
        final_decision = "HOLD"
    if (force_sell or take_profit) and final_decision != "SELL":
        final_decision = "SELL"

    return {
        "ticker":            ticker,
        "decision":          final_decision,
        "weighted_score":    round(score, 4),
        "chairman_rationale": chairman_out.get("chairman_rationale", "No rationale provided."),
        "risk_off":          risk_off,
        "spy_above_200d":    spy_above_200d,
        "active_weights":    weights,
        "risk_manager_veto": risk_vote.get("veto"),
        "force_sell":        force_sell,
        "take_profit":       take_profit,
        "risk_manager_reason": risk_vote.get("reason"),
        "agent_votes": [
            {
                "agent_name": v.get("agent"),
                "action":     v.get("action", "HOLD"),
                "confidence": v.get("confidence", 0.0),
                "rationale":  v.get("rationale", ""),
                "veto":       v.get("veto", False),
            }
            for v in [
                *agent_votes,
                {**risk_vote, "agent": "risk_manager", "action": "SELL" if (force_sell or take_profit) else "HOLD",
                 "rationale": risk_vote.get("reason", "")},
            ]
        ],
    }


async def run_full_committee(watchlist: list = None) -> list:
    if not is_market_open():
        print("Market is closed — skipping committee session")
        return []

    tickers = watchlist or WATCHLIST

    try:
        portfolio = await get_portfolio()
        async with AsyncSessionLocal() as db:
            await save_portfolio_snapshot(db, portfolio)
            peak_value = await get_peak_portfolio_value(db)
    except Exception as e:
        print(f"Portfolio fetch failed: {e}")
        portfolio  = {"total_value": 0, "cash": 0, "positions": []}
        peak_value = 0.0

    results = []
    for ticker in tickers:
        try:
            result = await run_committee_for_ticker(ticker, portfolio, peak_value)
            results.append(result)
            flags = []
            if result.get("force_sell"):   flags.append("STOP-LOSS")
            if result.get("take_profit"):  flags.append("TAKE-PROFIT")
            if result.get("risk_off"):     flags.append("RISK-OFF")
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            print(f"[{ticker}] {result['decision']} | score={result['weighted_score']:.2f} | order={result['order_placed']}{flag_str}")
        except Exception as e:
            print(f"[{ticker}] Session failed: {e}")

    return results
