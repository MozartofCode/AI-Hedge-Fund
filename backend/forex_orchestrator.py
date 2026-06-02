"""
Forex Committee Orchestrator.
Mirrors orchestrator.py but for currency pairs.

Agents: fx_technician (0.35), fx_carry (0.30), fx_macro (0.35)
Risk:   fx_risk_manager (pure logic, no weight)
Chairman: Haiku for scheduled runs, Sonnet for on-demand analysis
"""
import asyncio
import json
import os
from datetime import datetime

from backend.agents import fx_technician, fx_carry, fx_macro, fx_risk_manager
from backend.agents.base_agent import (
    call_claude, CHAIRMAN_MODEL, CHAIRMAN_SCHEDULE_MODEL, get_daily_spend,
)
from backend.broker.forex_broker import get_portfolio, place_order, close_position, is_forex_market_open
from backend.data.forex_client import FOREX_PAIRS
from backend.db.session import AsyncSessionLocal
from backend.db.crud import (
    create_session, save_agent_vote, finalize_session, log_trade,
    get_peak_portfolio_value,
)

# ── Decision thresholds ───────────────────────────────────────────────────────
FX_BUY_THRESHOLD  = 0.52   # match stock threshold — generate more signals
FX_SELL_THRESHOLD = 0.48   # raised from 0.45 — close positions faster on fade

_FX_WEIGHTS = {
    "fx_technician": 0.35,
    "fx_carry":      0.30,
    "fx_macro":      0.35,
}

# ── Chairman prompts ──────────────────────────────────────────────────────────

FX_CHAIRMAN_SYSTEM = """You are the Chairman of an AI forex trading committee. Three agents voted on this currency pair.
Write for a regular investor — plain English, no jargon. Be direct and specific.

Return ONLY valid JSON — no markdown, no explanation:
{
  "decision": "BUY" | "SELL" | "HOLD",
  "pair": "...",
  "direction": "long" | "short",
  "position_size_pct": 2-8,
  "order_type": "market",
  "chairman_rationale": "Exactly 3 bullet lines:\\n• 📈 Why: [most compelling reason]\\n• ⚠️ Risk: [biggest thing that could go wrong]\\n• 👀 Watch: [one rate or event to monitor]"
}

BUY = open long the base currency. SELL = open short the base currency. HOLD = do nothing.
BUY if score > 0.55 and no risk veto. SELL if score < 0.45 or risk veto says force_close.
Position sizing: 2-3% moderate conviction, 4-6% strong, 7-8% highest conviction.
Always respect the Risk Manager's veto and force_close signals."""

FX_CHAIRMAN_ANALYSIS_SYSTEM = """You are the Chairman of an AI forex trading committee. Three agents voted on this currency pair.
Write for a regular investor — plain English, no jargon.

Return ONLY valid JSON — no markdown, no explanation:
{
  "decision": "BUY" | "SELL" | "HOLD",
  "pair": "...",
  "direction": "long" | "short",
  "position_size_pct": 2-8,
  "order_type": "market",
  "chairman_rationale": "Exactly 3 bullet lines:\\n• 📈 Why: [most compelling reason]\\n• ⚠️ Risk: [biggest thing that could go wrong]\\n• 👀 Watch: [one rate or event to monitor]",
  "rate_targets": {"1w": 0.0, "1m": 0.0, "3m": 0.0},
  "stop_loss_rate": 0.0
}

BUY if score > 0.55. SELL if score < 0.45. HOLD otherwise.
rate_targets: realistic exchange rate levels (e.g. if EURUSD = 1.0820, 1w = 1.0850).
stop_loss_rate: rate where the position should be closed to limit losses."""


# ── Score helpers ─────────────────────────────────────────────────────────────

def _action_score(action: str, confidence: float) -> float:
    """Map BUY/SELL/HOLD + confidence → 0-1 bullish score."""
    if action == "BUY":
        return 0.5 + confidence * 0.5
    if action == "SELL":
        return 0.5 - confidence * 0.5
    return 0.5   # HOLD


def _weighted_score(votes: list, weights: dict) -> float:
    total_w = score_w = 0.0
    for v in votes:
        agent = v.get("agent", "")
        w = weights.get(agent, 0.0)
        if w <= 0:
            continue
        s = _action_score(v.get("action", "HOLD"), v.get("confidence", 0.0))
        score_w += s * w
        total_w += w
    return round(score_w / total_w, 4) if total_w > 0 else 0.5


# ── Committee for a single pair ───────────────────────────────────────────────

async def run_committee_for_pair(
    pair: str, portfolio: dict, peak_value: float
) -> dict:
    """
    Run 3 agents + risk check + Chairman for one currency pair.
    Places an order if appropriate and market is open.
    Persists session + votes + trade to DB.
    """
    # Stage 1: tech + macro in parallel (both fetch yfinance history)
    tech_vote, macro_vote = await asyncio.gather(
        asyncio.to_thread(fx_technician.get_vote, pair),
        asyncio.to_thread(fx_macro.get_vote, pair),
    )

    # Stage 2: carry uses momentum_score from tech (avoids redundant fetch)
    momentum_score = tech_vote.get("momentum_score", 0.5)
    carry_vote = await asyncio.to_thread(fx_carry.get_vote, pair, momentum_score)

    agent_votes = [tech_vote, carry_vote, macro_vote]

    # Score → preliminary direction
    score = _weighted_score(agent_votes, _FX_WEIGHTS)
    if score >= FX_BUY_THRESHOLD:
        prelim_direction = "long"
    elif score <= FX_SELL_THRESHOLD:
        prelim_direction = "short"
    else:
        prelim_direction = None   # HOLD

    # Risk manager check (pure logic)
    current_rate = tech_vote.get("current_rate")
    atr_pct      = tech_vote.get("atr_pct")
    risk_vote    = fx_risk_manager.get_vote(
        pair,
        portfolio=portfolio,
        peak_value=peak_value,
        atr_pct=atr_pct,
        current_rate=current_rate,
        direction=prelim_direction or "long",
    )

    force_close = risk_vote.get("force_close", False)
    take_profit = risk_vote.get("take_profit", False)
    veto        = risk_vote.get("veto", False)
    stop_loss_r = risk_vote.get("stop_loss_rate")

    # Detect position flip: score contradicts existing position direction → close it.
    # This must happen BEFORE the veto check so the correlation/duplicate veto
    # does not block exits (same fix as the stocks "no pyramid" veto bug).
    positions    = portfolio.get("positions", [])
    existing_pos = next((p for p in positions if p["pair"] == pair.upper()), None)
    score_dir    = "long" if score >= FX_BUY_THRESHOLD else ("short" if score <= FX_SELL_THRESHOLD else None)
    should_close = (
        existing_pos is not None
        and score_dir is not None
        and existing_pos["direction"] != score_dir
        and not force_close
        and not take_profit
    )

    # Final decision
    if force_close or take_profit or should_close:
        final_decision = "SELL"   # will call close_position()
    elif veto:
        final_decision = "HOLD"
    elif score >= FX_BUY_THRESHOLD:
        final_decision = "BUY"
    elif score <= FX_SELL_THRESHOLD:
        final_decision = "SELL"   # open new position (no existing opposite)
    else:
        final_decision = "HOLD"

    # Skip Chairman on plain HOLDs (cost optimisation — same as stock orchestrator)
    _plain_hold = (final_decision == "HOLD" and not force_close and not take_profit and not veto)
    if _plain_hold:
        chairman_out = {
            "decision":           "HOLD",
            "direction":          "long",
            "position_size_pct":  0,
            "chairman_rationale": (
                f"HOLD — no clear directional signal (score {score:.3f}). "
                f"(est. daily spend: ${get_daily_spend():.4f})"
            ),
            "rate_targets": None,
            "stop_loss_rate": None,
        }
    else:
        chairman_input = {
            "pair":                pair,
            "current_rate":        current_rate,
            "weighted_score":      score,
            "preliminary_decision": final_decision,
            "risk_manager_veto":   veto,
            "force_close":         force_close,
            "take_profit":         take_profit,
            "agent_votes": [
                {
                    "agent": v.get("agent"), "action": v.get("action"),
                    "confidence": v.get("confidence"), "rationale": v.get("rationale")
                }
                for v in agent_votes
            ],
        }
        chairman_out = call_claude(
            FX_CHAIRMAN_SYSTEM,
            f"Forex committee: {json.dumps(chairman_input)}",
            "fx_chairman",
            max_tokens=300,
            model=CHAIRMAN_SCHEDULE_MODEL,
        )

    chairman_rationale = chairman_out.get("chairman_rationale", "No rationale.")
    direction          = chairman_out.get("direction", "long" if final_decision == "BUY" else "short")
    position_pct       = chairman_out.get("position_size_pct", 3)

    # Persist to DB
    order_placed = False
    order_id     = None
    async with AsyncSessionLocal() as db:
        session = await create_session(db, pair, "FOREX")
        for v in [*agent_votes, {**risk_vote, "agent": "fx_risk_manager"}]:
            await save_agent_vote(db, session.id, {
                "agent":      v.get("agent", "unknown"),
                "action":     v.get("action", "HOLD"),
                "confidence": v.get("confidence", 0.0),
                "rationale":  v.get("rationale", ""),
                "raw_data":   v,
            })

    # Execute trade
    if final_decision in ("BUY", "SELL") and is_forex_market_open():
        try:
            if force_close or take_profit or should_close:
                # Close existing position cleanly (bypasses correlation-veto race)
                order = await close_position(pair)
            else:
                order = await place_order(pair, direction, position_pct, stop_loss_r)

            order_placed = True
            order_id     = order.get("order_id")

            async with AsyncSessionLocal() as db:
                await log_trade(db, session.id, {
                    "ticker":       pair,
                    "side":         order.get("side"),
                    "qty":          order.get("qty"),
                    "filled_price": order.get("price"),
                    "filled_at":    order.get("filled_at", datetime.utcnow()),
                    "order_id":     order_id,
                }, market="FOREX")
        except Exception as e:
            print(f"[forex_orchestrator] {pair} order failed: {e}")

    async with AsyncSessionLocal() as db:
        await finalize_session(db, session.id, {
            "decision":           final_decision,
            "chairman_rationale": chairman_rationale,
            "weighted_score":     score,
            "order_placed":       order_placed,
            "order_id":           order_id,
        })

    return {
        "pair":               pair,
        "decision":           final_decision,
        "direction":          direction,
        "weighted_score":     score,
        "chairman_rationale": chairman_rationale,
        "order_placed":       order_placed,
        "current_rate":       current_rate,
    }


# ── Analyze (on-demand, no order placed) ─────────────────────────────────────

async def analyze_pair(pair: str) -> dict:
    """
    On-demand pair analysis — same agents, Sonnet Chairman, no order.
    Returns rate targets + stop-loss for frontend display.
    """
    tech_vote, macro_vote = await asyncio.gather(
        asyncio.to_thread(fx_technician.get_vote, pair),
        asyncio.to_thread(fx_macro.get_vote, pair),
    )
    carry_vote = await asyncio.to_thread(
        fx_carry.get_vote, pair, tech_vote.get("momentum_score", 0.5)
    )
    agent_votes = [tech_vote, carry_vote, macro_vote]
    score       = _weighted_score(agent_votes, _FX_WEIGHTS)
    current_rate = tech_vote.get("current_rate")

    chairman_input = {
        "pair":           pair,
        "current_rate":   current_rate,
        "weighted_score": score,
        "carry_differential": carry_vote.get("carry_differential"),
        "momentum_score": tech_vote.get("momentum_score"),
        "risk_sentiment": macro_vote.get("risk_sentiment"),
        "agent_votes": [
            {"agent": v.get("agent"), "action": v.get("action"),
             "confidence": v.get("confidence"), "rationale": v.get("rationale")}
            for v in agent_votes
        ],
    }
    chairman_out = call_claude(
        FX_CHAIRMAN_ANALYSIS_SYSTEM,
        f"Forex analysis: {json.dumps(chairman_input)}",
        "fx_chairman",
        max_tokens=600,
        model=CHAIRMAN_MODEL,
    )

    return {
        "pair":               pair,
        "decision":           chairman_out.get("decision", "HOLD"),
        "direction":          chairman_out.get("direction", "long"),
        "weighted_score":     score,
        "chairman_rationale": chairman_out.get("chairman_rationale", ""),
        "rate_targets":       chairman_out.get("rate_targets"),
        "stop_loss_rate":     chairman_out.get("stop_loss_rate"),
        "current_rate":       current_rate,
        "carry_differential": carry_vote.get("carry_differential"),
        "agent_votes": [
            {
                "agent_name":  v.get("agent"),
                "action":      v.get("action", "HOLD"),
                "confidence":  v.get("confidence", 0.0),
                "rationale":   v.get("rationale", ""),
                "carry_differential": v.get("carry_differential"),
                "momentum_score": v.get("momentum_score"),
                "risk_sentiment": v.get("risk_sentiment"),
            }
            for v in agent_votes
        ],
    }


# ── Full committee run ────────────────────────────────────────────────────────

async def run_full_forex_committee() -> list:
    """Run committee for all FOREX_PAIRS. Called by scheduler."""
    if not is_forex_market_open():
        print("[FOREX] Market closed — skipping committee")
        return []

    portfolio = await get_portfolio()

    async with AsyncSessionLocal() as db:
        peak_value = await get_peak_portfolio_value(db, "FOREX")
    peak_value = max(peak_value, portfolio["total_value"])

    results = []
    for pair in FOREX_PAIRS:
        try:
            result = await run_committee_for_pair(pair, portfolio, peak_value)
            results.append(result)
            print(f"[FOREX] {pair}: {result['decision']} (score {result['weighted_score']:.3f})")
        except Exception as e:
            print(f"[FOREX] {pair} committee error: {e}")

    return results
