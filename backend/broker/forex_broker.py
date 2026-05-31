"""
Forex paper trading broker.
Positions are notional-USD-based (no share quantities).
P&L = (current_rate - entry_rate) / entry_rate * notional_usd  (long)
     = (entry_rate - current_rate) / entry_rate * notional_usd  (short)
"""
import uuid
from datetime import datetime

from backend.db.session import AsyncSessionLocal
from backend.db.crud import (
    get_forex_portfolio,
    get_forex_positions,
    get_forex_position,
    update_forex_cash,
    upsert_forex_position,
    delete_forex_position,
)
from backend.data.forex_client import get_current_rate, get_all_current_rates


# ── Market hours ──────────────────────────────────────────────────────────────

def is_forex_market_open() -> bool:
    """Forex trades Mon 00:00 UTC → Fri 22:00 UTC. Closed weekends."""
    from datetime import timezone
    now = datetime.now(timezone.utc)
    wd  = now.weekday()   # 0=Mon … 6=Sun
    if wd == 5:            # Saturday — always closed
        return False
    if wd == 6:            # Sunday — always closed
        return False
    if wd == 4 and now.hour >= 22:   # Friday after 22:00 UTC
        return False
    return True


# ── Portfolio ─────────────────────────────────────────────────────────────────

async def get_portfolio() -> dict:
    """
    Read cash + open positions from DB, enrich with live rates.
    Returns the same shape as paper_broker.get_portfolio() but forex-specific.
    """
    async with AsyncSessionLocal() as db:
        port_row  = await get_forex_portfolio(db)
        pos_rows  = await get_forex_positions(db)

    cash = port_row.cash if port_row else 1_000_000.0

    enriched = []
    total_pos_value = 0.0

    # Batch-fetch all rates once to avoid N+1 calls
    all_rates = {}
    try:
        all_rates = get_all_current_rates()
    except Exception:
        pass

    for pos in pos_rows:
        try:
            current_rate = all_rates.get(pos.pair) or get_current_rate(pos.pair)
            entry = pos.entry_rate
            if pos.direction == "long":
                pnl = (current_rate - entry) / entry * pos.notional_usd
            else:
                pnl = (entry - current_rate) / entry * pos.notional_usd

            current_value = pos.notional_usd + pnl
            pnl_pct = pnl / pos.notional_usd if pos.notional_usd > 0 else 0.0

        except Exception:
            current_rate = pos.entry_rate
            pnl          = 0.0
            current_value = pos.notional_usd
            pnl_pct      = 0.0

        enriched.append({
            "pair":            pos.pair,
            "direction":       pos.direction,
            "notional_usd":    round(pos.notional_usd, 2),
            "entry_rate":      round(pos.entry_rate, 6),
            "current_rate":    round(current_rate, 6),
            "unrealized_pl":   round(pnl, 2),
            "unrealized_plpc": round(pnl_pct, 4),
            "stop_loss_rate":  pos.stop_loss_rate,
        })
        total_pos_value += current_value

    return {
        "total_value":  round(cash + total_pos_value, 2),
        "cash":         round(cash, 2),
        "buying_power": round(cash, 2),
        "positions":    enriched,
    }


# ── Order execution ───────────────────────────────────────────────────────────

async def place_order(
    pair: str,
    direction: str,
    position_size_pct: float,
    stop_loss_rate: float = None,
) -> dict:
    """
    Execute a forex paper trade.
    direction: "long" | "short"
    position_size_pct: % of total portfolio value to deploy as notional USD.
    """
    try:
        current_rate = get_current_rate(pair)
    except Exception as e:
        raise ValueError(f"Cannot place {pair} order — rate unavailable: {e}")

    async with AsyncSessionLocal() as db:
        port_row  = await get_forex_portfolio(db)
        pos_rows  = await get_forex_positions(db)

        cash = port_row.cash if port_row else 1_000_000.0

        # Total portfolio value (cash + position values)
        total_value = cash
        for pos in pos_rows:
            try:
                r = get_current_rate(pos.pair)
                e = pos.entry_rate
                if pos.direction == "long":
                    pnl = (r - e) / e * pos.notional_usd
                else:
                    pnl = (e - r) / e * pos.notional_usd
                total_value += pos.notional_usd + pnl
            except Exception:
                total_value += pos.notional_usd

        notional = round(total_value * (position_size_pct / 100), 2)
        notional = max(1000.0, notional)   # minimum $1,000 notional

        # Opening a new position or adding to existing
        existing = await get_forex_position(db, pair)
        if direction in ("long", "short"):
            if existing and existing.direction == direction:
                raise ValueError(f"Position in {pair} {direction} already open")
            if existing and existing.direction != direction:
                # Close opposite position first
                proceeds = existing.notional_usd + (
                    (current_rate - existing.entry_rate) / existing.entry_rate * existing.notional_usd
                    if existing.direction == "long"
                    else (existing.entry_rate - current_rate) / existing.entry_rate * existing.notional_usd
                )
                await update_forex_cash(db, cash + proceeds)
                await delete_forex_position(db, pair)
                cash += proceeds

            if cash < notional:
                raise ValueError(
                    f"Insufficient cash (${cash:,.2f}) for ${notional:,.2f} {pair} trade"
                )
            await update_forex_cash(db, cash - notional)
            await upsert_forex_position(db, pair, direction, notional, current_rate, stop_loss_rate)

        side_label = "buy" if direction == "long" else "sell_short"

    return {
        "order_id":   f"fx-{uuid.uuid4().hex[:8]}",
        "pair":       pair,
        "direction":  direction,
        "side":       side_label,
        "qty":        notional,           # notional_usd used as qty for Trade table
        "price":      current_rate,
        "notional":   notional,
        "status":     "filled",
        "filled_at":  datetime.utcnow(),
    }


async def close_position(pair: str) -> dict:
    """Close an existing forex position — returns proceeds."""
    try:
        current_rate = get_current_rate(pair)
    except Exception as e:
        raise ValueError(f"Cannot close {pair} — rate unavailable: {e}")

    async with AsyncSessionLocal() as db:
        port_row = await get_forex_portfolio(db)
        cash     = port_row.cash if port_row else 0.0
        pos      = await get_forex_position(db, pair)

        if not pos:
            raise ValueError(f"No open {pair} position to close")

        if pos.direction == "long":
            pnl = (current_rate - pos.entry_rate) / pos.entry_rate * pos.notional_usd
        else:
            pnl = (pos.entry_rate - current_rate) / pos.entry_rate * pos.notional_usd

        proceeds = pos.notional_usd + pnl
        await update_forex_cash(db, cash + proceeds)
        await delete_forex_position(db, pair)

        side_label = "sell" if pos.direction == "long" else "buy_cover"

    return {
        "order_id":  f"fx-{uuid.uuid4().hex[:8]}",
        "pair":      pair,
        "direction": f"close_{pos.direction}",
        "side":      side_label,
        "qty":       pos.notional_usd,
        "price":     current_rate,
        "pnl":       round(pnl, 2),
        "proceeds":  round(proceeds, 2),
        "status":    "filled",
        "filled_at": datetime.utcnow(),
    }
