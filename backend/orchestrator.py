import asyncio
import json
import os
from datetime import datetime

from backend.agents.base_agent import (
    call_claude, CHAIRMAN_MODEL, CHAIRMAN_SCHEDULE_MODEL, get_daily_spend,
    scheduled_agent_config, scheduled_chairman_config,
)
from backend.agents import technician, fundamentalist, newshound, macro_watcher, risk_manager
from backend.broker.paper_broker import get_portfolio, place_order
from backend.db.session import AsyncSessionLocal
from backend.db.crud import (
    create_session, save_agent_vote, finalize_session,
    log_trade, save_portfolio_snapshot, get_peak_portfolio_value,
)
from backend.markets import MARKETS, is_market_open
from backend.screener import get_watchlist
from backend.notifications.slack_notifier import notify_trade

# ── Base agent weights (regime-adjusted in _get_weights) ─────────────────────
_BASE_WEIGHTS = {
    "technician":     0.30,
    "fundamentalist": 0.25,
    "newshound":      0.20,
    "macro_watcher":  0.25,
}

# ── Decision thresholds ───────────────────────────────────────────────────────
BUY_THRESHOLD  = 0.52   # lowered from 0.60 — trigger on moderate conviction
SELL_THRESHOLD = 0.45   # raised from 0.35 — sell faster when signal fades, more churn

# ── Conviction-based position sizing ─────────────────────────────────────────
_BASE_POSITION_PCT = 3.0    # minimum size — conviction scaling drives higher
_MAX_POSITION_PCT  = 50.0   # no artificial cap — go big on the best setups

# ── Chairman prompt for scheduled committee runs (lean — no price targets) ────
# Cost-optimised: only fires on BUY/SELL. Max ~300 output tokens.
CHAIRMAN_SYSTEM = """You are the Chairman of an AI investment committee. Five agents voted on this stock.
Write for a regular investor — plain English, no jargon. Be direct and specific.

Return ONLY valid JSON — no markdown, no explanation:
{
  "decision": "BUY" | "SELL" | "HOLD",
  "ticker": "...",
  "position_size_pct": 0-50,
  "order_type": "market",
  "chairman_rationale": "Exactly 3 bullet lines:\n• 📈 Why: [most compelling reason — specific]\n• ⚠️ Risk: [biggest thing that could go wrong]\n• 👀 Watch: [one metric or event to monitor]"
}

Rules:
- BUY if score > 0.52 and no veto. SELL if score < 0.45 or risk veto. HOLD otherwise.
- Sizing: 3-5% moderate conviction, 10-25% strong, 25-50% highest conviction (all agents aligned + squeeze setup + consecutive beats).
- Be aggressive — maximise return. Concentrate in the best setups.
- Always respect the Risk Manager's veto."""

# ── Chairman prompt for on-demand analysis (full — includes price targets) ────
# Used only in analyze_ticker() — user explicitly requested it, worth the tokens.
CHAIRMAN_ANALYSIS_SYSTEM = """You are the Chairman of an AI investment committee. Five agents voted on this stock.
Write for a regular investor — plain English, no jargon. Be direct and specific.

Return ONLY valid JSON — no markdown, no explanation:
{
  "decision": "BUY" | "SELL" | "HOLD",
  "ticker": "...",
  "position_size_pct": 0-50,
  "order_type": "market",
  "chairman_rationale": "Exactly 3 bullet lines:\n• 📈 Why: [most compelling reason — specific]\n• ⚠️ Risk: [biggest thing that could go wrong]\n• 👀 Watch: [one metric or event to monitor]",
  "price_targets": {
    "1m":  0.00,
    "6m":  0.00,
    "1y":  0.00
  },
  "stop_loss": 0.00
}

Price target rules (use current_price from input):
- BUY: 1m = near-term momentum, 6m/1y = thesis playing out
- SELL: show expected decline. HOLD: tight range around current price.
- stop_loss: typically 8-12% below current for BUY. All values in actual dollars.

Rules:
- BUY if score > 0.52 and no veto. SELL if score < 0.45 or risk veto. HOLD otherwise.
- Sizing: 3-5% moderate, 10-25% strong, 25-50% highest conviction.
- Be aggressive — maximise return. Always respect the Risk Manager's veto."""


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
    HOLD = genuinely neutral (0.5) regardless of confidence.
    """
    if action == "BUY":
        return confidence
    if action == "SELL":
        return 1.0 - confidence
    return 0.5


def _weighted_score(votes: list, weights: dict) -> float:
    # Exclude agents that errored — their signature is action=HOLD + confidence=0.0
    # This is critical for non-US markets where FMP/Finnhub coverage is sparse;
    # failed agents should not drag the score toward 0.5 and kill valid signals.
    active = [
        v for v in votes
        if v.get("agent") in weights
        and not (v.get("action") == "HOLD" and float(v.get("confidence", 1.0)) == 0.0)
    ]
    if not active:
        return 0.5   # all agents failed — neutral
    total_w = sum(weights.get(v["agent"], 0) for v in active)
    raw = sum(
        weights.get(v["agent"], 0) * _action_score(v.get("action", "HOLD"), float(v.get("confidence", 0.5)))
        for v in active
    )
    return round(raw / total_w, 4) if total_w > 0 else 0.5


def _conviction_position_size(score: float, atr_pct: float = None) -> float:
    """
    Scale position size with conviction: 5% at threshold → 12% at perfect score.
    ATR-based volatility cap: high-ATR stocks get smaller positions to keep
    consistent dollar risk per trade regardless of the stock's daily swing size.
    """
    conviction = (score - BUY_THRESHOLD) / (1.0 - BUY_THRESHOLD)
    size = _BASE_POSITION_PCT + conviction * (_MAX_POSITION_PCT - _BASE_POSITION_PCT)
    size = round(min(_MAX_POSITION_PCT, max(_BASE_POSITION_PCT, size)), 1)
    # Volatility cap — ATR > 4% daily = very volatile (SMCI, MSTR, TSLA-like)
    if atr_pct is not None:
        if atr_pct > 4.0:
            size = min(size, 5.0)    # cap at 5% for very high-volatility stocks
        elif atr_pct > 2.5:
            size = min(size, 8.0)    # cap at 8% for moderately volatile stocks
    return size


async def run_committee_for_ticker(
    ticker: str, portfolio: dict, peak_value: float, market: str = 'US'
) -> dict:
    # Run 4 data agents in parallel — automatic trader uses the scheduled provider
    # (Groq by default; configurable via SCHEDULED_PROVIDER).
    ag_model, ag_provider = scheduled_agent_config()
    tech_vote, fund_vote, news_vote, macro_vote = await asyncio.gather(
        asyncio.to_thread(technician.get_vote, ticker, ag_model, ag_provider),
        asyncio.to_thread(fundamentalist.get_vote, ticker, ag_model, ag_provider),
        asyncio.to_thread(newshound.get_vote, ticker, ag_model, ag_provider),
        asyncio.to_thread(macro_watcher.get_vote, ticker, ag_model, ag_provider),
    )

    agent_votes = [tech_vote, fund_vote, news_vote, macro_vote]
    risk_vote   = risk_manager.get_vote(ticker, portfolio=portfolio, peak_value=peak_value)

    # ── Regime-aware weights ─────────────────────────────────────────────────
    risk_off       = macro_vote.get("risk_off", False)
    vix_raw        = macro_vote.get("vix_raw")
    spy_above_200d = macro_vote.get("spy_above_200d")
    weights        = _get_weights(risk_off, vix_raw, spy_above_200d)
    score          = _weighted_score(agent_votes, weights)
    atr_pct        = tech_vote.get("atr_pct")   # for volatility-adjusted sizing

    # ── Decision logic (stop-loss / profit-target override first) ────────────
    force_sell   = risk_vote.get("force_sell", False)
    take_profit  = risk_vote.get("take_profit", False)
    holds_ticker = any(p["ticker"] == ticker for p in portfolio.get("positions", []))

    if force_sell or take_profit:
        decision      = "SELL"
        position_size = _BASE_POSITION_PCT
    elif score <= SELL_THRESHOLD and holds_ticker:
        # Score-based exit: check BEFORE veto so "no pyramid" veto doesn't block sells
        decision      = "SELL"
        position_size = _BASE_POSITION_PCT
    elif risk_vote.get("veto"):
        decision      = "HOLD"
        position_size = 0.0
    elif score >= BUY_THRESHOLD:
        decision      = "BUY"
        position_size = _conviction_position_size(score, atr_pct)
    else:
        decision      = "HOLD"
        position_size = 0.0

    # ── Chairman rationale via Claude (only on BUY / SELL — skip HOLDs) ─────────
    # HOLDs are ~85% of all tickers. Skipping Sonnet on HOLDs cuts costs ~80%.
    final_decision = decision
    final_size     = position_size
    rationale      = f"HOLD — score {score:.2f} is between thresholds. No action."

    if decision in ("BUY", "SELL") or force_sell or take_profit:
        chairman_input = {
            "ticker":              ticker,
            "market":              market.upper(),
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
        ch_model, ch_provider = scheduled_chairman_config()
        chairman_out = call_claude(
            CHAIRMAN_SYSTEM,
            f"Committee analysis: {json.dumps(chairman_input)}",
            "chairman",
            max_tokens=300,   # concise — 300 tokens is plenty for a 3-bullet rationale
            model=ch_model,        # Groq by default (SCHEDULED_PROVIDER), Haiku fallback
            provider=ch_provider,
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
        session = await create_session(db, ticker, market)

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
        market_cfg   = MARKETS.get(market.upper(), MARKETS["US"])

        if is_market_open(market) and final_decision in ("BUY", "SELL") and final_size > 0:
            try:
                order        = await place_order(ticker, final_decision.lower(), final_size, market)
                order_placed = True
                order_id     = order.get("order_id")
                await log_trade(db, session.id, {
                    "ticker":       ticker,
                    "side":         final_decision.lower(),
                    "qty":          order.get("qty"),
                    "filled_price": order.get("price"),
                    "filled_at":    datetime.utcnow(),
                    "order_id":     order_id,
                }, market)

                # Slack only for US market (or markets with slack_notify=True)
                if market_cfg.get("slack_notify", False):
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
        "market":              market.upper(),
        "decision":            final_decision,
        "weighted_score":      score,
        "chairman_rationale":  rationale,
        "order_placed":        order_placed,
        "risk_off":            risk_off,
        "risk_manager_veto":   risk_vote.get("veto"),
        "force_sell":          force_sell,
        "take_profit":         take_profit,
    }


async def analyze_ticker(ticker: str, market: str = 'US') -> dict:
    """
    Run all 5 agents + Chairman for a single ticker.
    Analysis-only — no order placed, works when market is closed.
    """
    portfolio = await get_portfolio(market)
    async with AsyncSessionLocal() as db:
        peak_value = await get_peak_portfolio_value(db, market)

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
    atr_pct        = tech_vote.get("atr_pct")

    force_sell  = risk_vote.get("force_sell", False)
    take_profit = risk_vote.get("take_profit", False)
    holds_ticker = any(p["ticker"] == ticker for p in portfolio.get("positions", []))

    if force_sell or take_profit:
        decision      = "SELL"
        position_size = _BASE_POSITION_PCT
    elif score <= SELL_THRESHOLD and holds_ticker:
        # Score-based exit: check BEFORE veto so "no pyramid" veto doesn't block sells
        decision      = "SELL"
        position_size = _BASE_POSITION_PCT
    elif risk_vote.get("veto"):
        decision      = "HOLD"
        position_size = 0.0
    elif score >= BUY_THRESHOLD:
        decision      = "BUY"
        position_size = _conviction_position_size(score, atr_pct)
    else:
        decision      = "HOLD"
        position_size = 0.0

    current_price = tech_vote.get("current_price")

    # ── Chairman call (Sonnet — full quality for user-requested analysis) ──────
    # Skip on plain HOLD to save ~$0.013 per call — only fire on actionable signals.
    _plain_hold = (decision == "HOLD" and not force_sell and not take_profit
                   and not risk_vote.get("veto"))

    if _plain_hold:
        # Return a clean HOLD without spending a Sonnet token.
        rationale_plain = (
            f"HOLD — weighted score {score:.2f} is between thresholds "
            f"(BUY>{BUY_THRESHOLD}, SELL<{SELL_THRESHOLD}). "
            f"No dominant signal from the committee. "
            f"(est. daily spend so far: ${get_daily_spend():.4f})"
        )
        chairman_out = {
            "decision":           "HOLD",
            "position_size_pct":  0,
            "chairman_rationale": rationale_plain,
            "price_targets":      None,
            "stop_loss":          None,
        }
    else:
        chairman_input = {
            "ticker":              ticker,
            "current_price":       current_price,
            "market":              market.upper(),
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
            CHAIRMAN_ANALYSIS_SYSTEM,
            f"Committee analysis: {json.dumps(chairman_input)}",
            "chairman",
            max_tokens=600,   # on-demand analysis — include price targets, worth the tokens
            model=CHAIRMAN_MODEL,
        )

    final_decision = chairman_out.get("decision", decision)
    if risk_vote.get("veto") and final_decision == "BUY":
        final_decision = "HOLD"
    if (force_sell or take_profit) and final_decision != "SELL":
        final_decision = "SELL"

    # ── Assemble valuation + section data from agent votes ───────────────────
    valuation_extras = {
        "company_name":     fund_vote.get("company_name"),
        "spot_price":       fund_vote.get("spot_price") or current_price,
        "dcf_price":        fund_vote.get("dcf_price"),
        "ws_price":         fund_vote.get("ws_price"),
        "ws_price_high":    fund_vote.get("ws_price_high"),
        "ws_price_low":     fund_vote.get("ws_price_low"),
        "ws_upside_pct":    fund_vote.get("ws_upside_pct"),
        "ws_ci_lo":         fund_vote.get("ws_ci_lo"),
        "ws_ci_hi":         fund_vote.get("ws_ci_hi"),
        "valuation_signal": fund_vote.get("valuation_signal"),
        "sections": {
            "valuation":  fund_vote.get("valuation_section", {}),
            "financial":  fund_vote.get("financial_section", {}),
            "newsworthy": {
                "news_sentiment":      news_vote.get("news_sentiment_score"),
                "article_count_14d":   news_vote.get("article_count_14d"),
                "consecutive_beats":   news_vote.get("consecutive_beats"),
                "insider_mspr":        news_vote.get("insider_mspr"),
                "squeeze_risk":        news_vote.get("squeeze_risk_score"),
                "sentiment_divergence": news_vote.get("sentiment_divergence"),
                "unusual_call_activity": news_vote.get("unusual_call_activity"),
                "short_interest_pct":  news_vote.get("short_interest_pct"),
                "days_to_cover":       news_vote.get("days_to_cover"),
                "analyst_upgrades":    news_vote.get("analyst_upgrades_30d"),
                "analyst_downgrades":  news_vote.get("analyst_downgrades_30d"),
                "recent_headlines":    news_vote.get("recent_headlines", []),
            },
        },
    }

    return {
        "ticker":            ticker,
        "market":            market.upper(),
        "decision":          final_decision,
        "weighted_score":    round(score, 4),
        "chairman_rationale": chairman_out.get("chairman_rationale", "No rationale provided."),
        "price_targets":     chairman_out.get("price_targets"),
        "stop_loss":         chairman_out.get("stop_loss"),
        "current_price":     current_price,
        "risk_off":          risk_off,
        "spy_above_200d":    spy_above_200d,
        "active_weights":    weights,
        "risk_manager_veto": risk_vote.get("veto"),
        "force_sell":        force_sell,
        "take_profit":       take_profit,
        "risk_manager_reason": risk_vote.get("reason"),
        **valuation_extras,
        "agent_votes": [
            {
                "agent_name": v.get("agent"),
                "action":     v.get("action", "HOLD"),
                "confidence": v.get("confidence", 0.0),
                "rationale":  v.get("rationale", ""),
                "veto":       v.get("veto", False),
                # Pass through sub-scores for richer agent tab display
                "valuation_score":     v.get("valuation_score"),
                "growth_score":        v.get("growth_score"),
                "profitability_score": v.get("profitability_score"),
                "revisions_score":     v.get("revisions_score"),
                "risk_off":            v.get("risk_off"),
            }
            for v in [
                *agent_votes,
                {**risk_vote, "agent": "risk_manager",
                 "action": "SELL" if (force_sell or take_profit) else "HOLD",
                 "rationale": risk_vote.get("reason", "")},
            ]
        ],
    }


async def run_full_committee(market: str = 'US') -> list:
    if not is_market_open(market):
        print(f"[{market}] Market is closed — skipping committee session")
        return []

    market_cfg = MARKETS.get(market.upper(), MARKETS["US"])
    # Dynamic screener — free pre-filter, narrows full market to top candidates.
    # Default 30 tickers keeps scheduled runs well under $1/day.
    # Override with COMMITTEE_MAX_TICKERS env var (e.g. set to 50 if budget allows).
    _max = int(os.getenv("COMMITTEE_MAX_TICKERS", "30"))
    tickers    = get_watchlist(market, max_tickers=_max)

    try:
        portfolio = await get_portfolio(market)
        async with AsyncSessionLocal() as db:
            await save_portfolio_snapshot(db, portfolio, market)
            peak_value = await get_peak_portfolio_value(db, market)
    except Exception as e:
        print(f"[{market}] Portfolio fetch failed: {e}")
        portfolio  = {"total_value": 0, "cash": 0, "positions": []}
        peak_value = 0.0

    results = []
    for ticker in tickers:
        try:
            result = await run_committee_for_ticker(ticker, portfolio, peak_value, market)
            results.append(result)
            flags = []
            if result.get("force_sell"):   flags.append("STOP-LOSS")
            if result.get("take_profit"):  flags.append("TAKE-PROFIT")
            if result.get("risk_off"):     flags.append("RISK-OFF")
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            print(f"[{market}][{ticker}] {result['decision']} | score={result['weighted_score']:.2f} | order={result['order_placed']}{flag_str}")
        except Exception as e:
            print(f"[{market}][{ticker}] Session failed: {e}")

    return results
