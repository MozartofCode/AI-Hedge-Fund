"""
FX Risk Manager — pure logic, no Claude call.
Mirrors risk_manager.py pattern for stocks.

Checks:
- Portfolio drawdown limit (15%)
- Maximum open positions (5)
- Correlation veto (don't hold correlated pairs in same direction)
- Duplicate position check
- Per-position stop-loss (1.5× ATR)
- Take-profit trigger (50% gain on notional)
"""
import math
from backend.data.forex_client import CORRELATED_PAIRS

MAX_FOREX_POSITIONS = 5
MAX_DRAWDOWN_PCT    = 15.0
STOP_LOSS_ATR_MULT  = 1.5
TAKE_PROFIT_PCT     = 50.0   # close position after 50% gain on notional


def get_vote(
    pair: str,
    portfolio: dict,
    peak_value: float,
    atr_pct: float = None,
    current_rate: float = None,
    direction: str = "long",
) -> dict:
    """
    portfolio: dict from forex_broker.get_portfolio()
    peak_value: highest total_value ever recorded (for drawdown calc)
    atr_pct: ATR as % of current rate (from fx_technician)
    current_rate: current exchange rate (from fx_technician)
    direction: proposed direction ("long" | "short")
    """
    positions     = portfolio.get("positions", [])
    total_value   = portfolio.get("total_value", 0.0)
    pair_upper    = pair.upper()

    veto       = False
    force_close = False
    take_profit = False
    reason      = "No alerts"
    stop_loss_rate = None

    # ── 1. Portfolio drawdown check ───────────────────────────────────────────
    if peak_value and peak_value > 0:
        drawdown_pct = (peak_value - total_value) / peak_value * 100
        if drawdown_pct >= MAX_DRAWDOWN_PCT:
            veto = True
            reason = f"Portfolio drawdown {drawdown_pct:.1f}% exceeds {MAX_DRAWDOWN_PCT}% limit"

    # ── 2. Max positions check ────────────────────────────────────────────────
    if not veto and len(positions) >= MAX_FOREX_POSITIONS:
        # Check if this pair is already open — if so, it's a close, not a new open
        already_open = any(p["pair"] == pair_upper for p in positions)
        if not already_open:
            veto = True
            reason = f"Maximum {MAX_FOREX_POSITIONS} open forex positions reached"

    # ── 3. Duplicate position check ───────────────────────────────────────────
    if not veto:
        for pos in positions:
            if pos["pair"] == pair_upper:
                if pos["direction"] == direction:
                    veto = True
                    reason = f"Already holding {pair_upper} {direction} — duplicate position"
                break

    # ── 4. Correlation veto ───────────────────────────────────────────────────
    # Don't hold two correlated pairs in the same direction
    if not veto:
        for corr_group in CORRELATED_PAIRS:
            if pair_upper in corr_group:
                for pos in positions:
                    if pos["pair"] in corr_group and pos["direction"] == direction:
                        veto = True
                        reason = (
                            f"Correlation veto: already holding {pos['pair']} {direction} "
                            f"(correlated with {pair_upper})"
                        )
                        break
            if veto:
                break

    # ── 5. Per-position stop-loss and take-profit ─────────────────────────────
    for pos in positions:
        if pos["pair"] == pair_upper and current_rate:
            entry  = pos.get("entry_rate", current_rate)
            pnl_pc = (current_rate - entry) / entry * 100
            if pos["direction"] == "short":
                pnl_pc = -pnl_pc

            # Take-profit
            if pnl_pc >= TAKE_PROFIT_PCT:
                take_profit = True
                reason = f"Take profit triggered — {pnl_pc:.1f}% gain on {pair_upper}"

            # Stop-loss from stored stop_loss_rate
            sl = pos.get("stop_loss_rate")
            if sl:
                if pos["direction"] == "long"  and current_rate <= sl:
                    force_close = True
                    reason = f"Stop-loss hit — {pair_upper} rate {current_rate:.5f} ≤ stop {sl:.5f}"
                elif pos["direction"] == "short" and current_rate >= sl:
                    force_close = True
                    reason = f"Stop-loss hit — {pair_upper} rate {current_rate:.5f} ≥ stop {sl:.5f}"

    # ── 6. Compute stop-loss rate for new position ────────────────────────────
    if not veto and current_rate and atr_pct:
        try:
            atr_abs = current_rate * (atr_pct / 100)
            sl_distance = atr_abs * STOP_LOSS_ATR_MULT
            if direction == "long":
                stop_loss_rate = round(current_rate - sl_distance, 6)
            else:
                stop_loss_rate = round(current_rate + sl_distance, 6)
        except Exception:
            pass

    # Build final action
    if force_close or take_profit:
        action = "SELL"
    elif veto:
        action = "HOLD"
    else:
        action = "BUY"   # approved — orchestrator decides actual direction

    return {
        "agent":               "fx_risk_manager",
        "pair":                pair_upper,
        "action":              action,
        "confidence":          0.0,   # risk manager doesn't use confidence
        "rationale":           reason,
        "suggested_position_size_pct": 0,
        "veto":                veto,
        "force_close":         force_close,
        "take_profit":         take_profit,
        "stop_loss_rate":      stop_loss_rate,
        "portfolio_drawdown_pct": (
            round((peak_value - total_value) / peak_value * 100, 2)
            if peak_value and peak_value > 0 else 0.0
        ),
    }
