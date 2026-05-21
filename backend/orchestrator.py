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

WATCHLIST = ["AAPL", "NVDA", "MSFT", "TSLA", "AMZN", "META", "GOOGL", "JPM", "XOM", "SPY"]

_WEIGHTS = {
    "technician": 0.25,
    "fundamentalist": 0.20,
    "newshound": 0.20,
    "macro_watcher": 0.15,
}
_TOTAL_WEIGHT = sum(_WEIGHTS.values())   # 0.80

BUY_THRESHOLD = 0.60
SELL_THRESHOLD = 0.35

CHAIRMAN_SYSTEM = """You are the Chairman of an AI investment committee. You have received structured analysis from 5 specialized agents.
Weigh their arguments, respect the Risk Manager's constraints, and produce a final trade decision with a rationale that would satisfy a compliance officer.
Return ONLY a valid JSON object — no markdown, no explanation, just JSON:
{
  "decision": "BUY" | "SELL" | "HOLD",
  "ticker": "...",
  "position_size_pct": 0-10,
  "order_type": "market",
  "chairman_rationale": "3-4 sentences covering key signals, risk constraints, and reasoning"
}"""


def _action_score(action: str, confidence: float) -> float:
    if action == "BUY":
        return confidence
    if action == "SELL":
        return 1.0 - confidence
    return 0.5


def _weighted_score(votes: list, risk_off: bool) -> float:
    raw = 0.0
    for vote in votes:
        weight = _WEIGHTS.get(vote.get("agent"))
        if weight is None:
            continue
        confidence = float(vote.get("confidence", 0.5))
        if risk_off:
            confidence *= 0.80
        raw += weight * _action_score(vote.get("action", "HOLD"), confidence)
    return round(raw / _TOTAL_WEIGHT, 4)


async def run_committee_for_ticker(ticker: str, portfolio: dict, peak_value: float) -> dict:
    # Run 4 data agents in parallel (sync HTTP wrapped in threads)
    tech_vote, fund_vote, news_vote, macro_vote = await asyncio.gather(
        asyncio.to_thread(technician.get_vote, ticker),
        asyncio.to_thread(fundamentalist.get_vote, ticker),
        asyncio.to_thread(newshound.get_vote, ticker),
        asyncio.to_thread(macro_watcher.get_vote, ticker),
    )

    agent_votes = [tech_vote, fund_vote, news_vote, macro_vote]
    risk_vote = risk_manager.get_vote(ticker, portfolio=portfolio, peak_value=peak_value)

    risk_off = macro_vote.get("risk_off", False)
    score = _weighted_score(agent_votes, risk_off=risk_off)

    # Determine preliminary decision
    if risk_vote.get("veto"):
        decision = "HOLD"
        position_size = 0.0
    elif score >= BUY_THRESHOLD:
        decision = "BUY"
        position_size = float(risk_vote.get("approved_position_size_pct", 5.0))
    elif score <= SELL_THRESHOLD:
        holds_ticker = any(p["ticker"] == ticker for p in portfolio.get("positions", []))
        decision = "SELL" if holds_ticker else "HOLD"
        position_size = 5.0 if holds_ticker else 0.0
    else:
        decision = "HOLD"
        position_size = 0.0

    # Chairman rationale via Claude
    chairman_input = {
        "ticker": ticker,
        "weighted_score": score,
        "risk_off": risk_off,
        "risk_manager_veto": risk_vote.get("veto"),
        "risk_manager_reason": risk_vote.get("reason"),
        "preliminary_decision": decision,
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
    )

    final_decision = chairman_out.get("decision", decision)
    if risk_vote.get("veto") and final_decision == "BUY":
        final_decision = "HOLD"   # Hard-enforce veto

    try:
        final_size = float(chairman_out.get("position_size_pct", position_size))
    except (TypeError, ValueError):
        final_size = position_size

    rationale = chairman_out.get("chairman_rationale", "No rationale provided.")

    # Persist to DB
    async with AsyncSessionLocal() as db:
        session = await create_session(db, ticker)

        for vote in agent_votes:
            await save_agent_vote(db, session.id, {
                "agent": vote.get("agent", "unknown"),
                "action": vote.get("action", "HOLD"),
                "confidence": vote.get("confidence", 0.0),
                "rationale": vote.get("rationale", ""),
                "raw_data": vote,
            })
        await save_agent_vote(db, session.id, {
            "agent": "risk_manager",
            "action": "HOLD",
            "confidence": 0.0,
            "rationale": risk_vote.get("reason", ""),
            "raw_data": risk_vote,
        })

        order_placed = False
        order_id = None
        if is_market_open() and final_decision in ("BUY", "SELL") and final_size > 0:
            try:
                order = await place_order(ticker, final_decision.lower(), final_size)
                order_placed = True
                order_id = order.get("order_id")
                await log_trade(db, session.id, {
                    "ticker": ticker,
                    "side": final_decision.lower(),
                    "qty": order.get("qty"),
                    "filled_price": order.get("price"),
                    "filled_at": datetime.utcnow(),
                    "order_id": order_id,
                })
            except Exception as e:
                rationale += f" [Order failed: {e}]"

        await finalize_session(db, session.id, {
            "decision": final_decision,
            "chairman_rationale": rationale,
            "weighted_score": score,
            "order_placed": order_placed,
            "order_id": order_id,
        })

    return {
        "ticker": ticker,
        "decision": final_decision,
        "weighted_score": score,
        "chairman_rationale": rationale,
        "order_placed": order_placed,
        "risk_off": risk_off,
        "risk_manager_veto": risk_vote.get("veto"),
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
        portfolio = {"total_value": 0, "cash": 0, "positions": []}
        peak_value = 0.0

    results = []
    for ticker in tickers:
        try:
            result = await run_committee_for_ticker(ticker, portfolio, peak_value)
            results.append(result)
            print(f"[{ticker}] {result['decision']} | score={result['weighted_score']:.2f} | order={result['order_placed']}")
        except Exception as e:
            print(f"[{ticker}] Session failed: {e}")

    return results
