"""
Paper trading broker — replaces Alpaca entirely.
Prices come from yfinance (free, no API key).
Positions and cash are stored in PostgreSQL.
Starting balance: $1,000,000.
"""
import uuid
from datetime import datetime, time

import pytz
import yfinance as yf

from backend.db.session import AsyncSessionLocal
from backend.db.crud import (
    get_paper_portfolio,
    get_paper_positions,
    get_paper_position,
    update_paper_cash,
    upsert_paper_position,
    delete_paper_position,
    STARTING_CASH,
)

ET = pytz.timezone("America/New_York")


# ── Market hours ──────────────────────────────────────────────────────────────

def is_market_open() -> bool:
    now_et = datetime.now(ET)
    if now_et.weekday() >= 5:          # Saturday / Sunday
        return False
    return time(9, 30) <= now_et.time() <= time(16, 0)


# ── Price data (yfinance) ─────────────────────────────────────────────────────

def get_current_price(ticker: str) -> float:
    """Fetch the latest price for a ticker via yfinance."""
    try:
        stock = yf.Ticker(ticker)
        price = stock.fast_info.last_price
        if price and float(price) > 0:
            return round(float(price), 4)
        # Fallback: last close from 1-day history
        hist = stock.history(period="1d")
        if not hist.empty:
            return round(float(hist["Close"].iloc[-1]), 4)
    except Exception:
        pass
    raise ValueError(f"Could not fetch price for {ticker}")


def get_historical_bars(ticker: str, days: int = 30) -> list:
    """Return daily OHLCV bars for the past N days via yfinance."""
    try:
        hist = yf.Ticker(ticker).history(period=f"{days}d")
        if hist.empty:
            return []
        return [
            {
                "timestamp": date,
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": float(row["Volume"]),
            }
            for date, row in hist.iterrows()
        ]
    except Exception:
        return []


# ── Portfolio state ───────────────────────────────────────────────────────────

async def get_portfolio() -> dict:
    """Read cash + positions from DB, enrich with live prices."""
    async with AsyncSessionLocal() as db:
        portfolio = await get_paper_portfolio(db)
        positions_rows = await get_paper_positions(db)

    cash = portfolio.cash if portfolio else STARTING_CASH

    enriched = []
    total_market_value = 0.0
    for pos in positions_rows:
        try:
            price = get_current_price(pos.ticker)
            mkt_val = pos.qty * price
            cost_basis = pos.qty * pos.avg_cost
            unr_pl = mkt_val - cost_basis
            unr_plpc = unr_pl / cost_basis if cost_basis > 0 else 0.0
        except Exception:
            price = pos.avg_cost
            mkt_val = pos.qty * pos.avg_cost
            unr_pl = 0.0
            unr_plpc = 0.0
        enriched.append({
            "ticker": pos.ticker,
            "qty": pos.qty,
            "avg_entry_price": pos.avg_cost,
            "current_price": round(price, 4),
            "market_value": round(mkt_val, 2),
            "unrealized_pl": round(unr_pl, 2),
            "unrealized_plpc": round(unr_plpc, 4),
        })
        total_market_value += mkt_val

    return {
        "total_value": round(cash + total_market_value, 2),
        "cash": round(cash, 2),
        "buying_power": round(cash, 2),
        "positions": enriched,
    }


# ── Order execution ───────────────────────────────────────────────────────────

async def place_order(ticker: str, side: str, position_size_pct: float) -> dict:
    """
    Execute a paper trade.
    position_size_pct: percentage of total portfolio value to allocate.
    Returns an order-result dict compatible with what orchestrator expects.
    """
    if not is_market_open():
        raise ValueError("Market is closed — orders only accepted 9:30 am–4:00 pm ET")

    current_price = get_current_price(ticker)

    async with AsyncSessionLocal() as db:
        portfolio = await get_paper_portfolio(db)
        cash = portfolio.cash if portfolio else STARTING_CASH
        positions = await get_paper_positions(db)

        # Total portfolio value for position sizing
        total_value = cash
        for pos in positions:
            try:
                total_value += pos.qty * get_current_price(pos.ticker)
            except Exception:
                total_value += pos.qty * pos.avg_cost

        notional = round(total_value * (position_size_pct / 100), 2)
        qty = round(notional / current_price, 6)

        if side.lower() == "buy":
            if cash < notional:
                raise ValueError(
                    f"Insufficient cash (${cash:,.2f}) for ${notional:,.2f} order"
                )
            await update_paper_cash(db, cash - notional)

            existing = await get_paper_position(db, ticker)
            if existing:
                new_qty = existing.qty + qty
                new_avg = (
                    (existing.qty * existing.avg_cost) + (qty * current_price)
                ) / new_qty
                await upsert_paper_position(db, ticker, new_qty, new_avg)
            else:
                await upsert_paper_position(db, ticker, qty, current_price)

        else:  # sell
            existing = await get_paper_position(db, ticker)
            if not existing:
                raise ValueError(f"No open position in {ticker} to sell")

            sell_qty = min(qty, existing.qty)
            proceeds = round(sell_qty * current_price, 2)
            await update_paper_cash(db, cash + proceeds)

            remaining = existing.qty - sell_qty
            if remaining < 0.0001:
                await delete_paper_position(db, ticker)
            else:
                await upsert_paper_position(db, ticker, remaining, existing.avg_cost)

    return {
        "order_id": f"paper-{uuid.uuid4().hex[:8]}",
        "ticker": ticker,
        "side": side.lower(),
        "qty": qty,
        "price": current_price,
        "notional": notional,
        "status": "filled",
    }
