"""
Paper trading broker — replaces Alpaca entirely.
Prices come from yfinance (free, no API key).
Positions and cash are stored in PostgreSQL, keyed by market.
"""
import asyncio
import time
import uuid
from datetime import datetime

import yfinance as yf

# ── Portfolio cache (application-level, invalidated on buy/sell) ──────────────
_portfolio_cache: dict = {}   # key: market → {"data": ..., "expires": float}
_PORTFOLIO_CACHE_TTL = 60     # seconds

from backend.db.session import AsyncSessionLocal
from backend.db.crud import (
    get_paper_portfolio,
    get_paper_positions,
    get_paper_position,
    update_paper_cash,
    upsert_paper_position,
    delete_paper_position,
)
from backend.markets import is_market_open


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

def _invalidate_portfolio_cache(market: str):
    _portfolio_cache.pop(market.upper(), None)


async def get_portfolio(market: str = 'US') -> dict:
    """Read cash + positions from DB for a given market, enrich with live prices.
    Result is cached for 60 s and invalidated whenever a trade is placed."""
    mkt = market.upper()
    cached = _portfolio_cache.get(mkt)
    if cached and time.monotonic() < cached["expires"]:
        return cached["data"]

    async with AsyncSessionLocal() as db:
        portfolio = await get_paper_portfolio(db, market)
        positions_rows = await get_paper_positions(db, market)

    from backend.markets import MARKETS
    default_cash = MARKETS.get(market.upper(), MARKETS["US"])["starting_cash"]
    cash = portfolio.cash if portfolio else default_cash

    # Fetch every position's live price concurrently — yfinance is the slow part,
    # so running the calls in parallel turns an N-second load into ~1 call's worth.
    tickers = [pos.ticker for pos in positions_rows]
    fetched = await asyncio.gather(
        *(asyncio.to_thread(get_current_price, t) for t in tickers),
        return_exceptions=True,
    )
    price_map = {
        t: p for t, p in zip(tickers, fetched)
        if not isinstance(p, Exception)
    }

    enriched = []
    total_market_value = 0.0
    for pos in positions_rows:
        price = price_map.get(pos.ticker)
        if price:
            mkt_val = pos.qty * price
            cost_basis = pos.qty * pos.avg_cost
            unr_pl = mkt_val - cost_basis
            unr_plpc = unr_pl / cost_basis if cost_basis > 0 else 0.0
        else:
            # Price fetch failed — fall back to cost basis (no unrealized P&L)
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

    result = {
        "market": mkt,
        "total_value": round(cash + total_market_value, 2),
        "cash": round(cash, 2),
        "buying_power": round(cash, 2),
        "positions": enriched,
    }
    _portfolio_cache[mkt] = {"data": result, "expires": time.monotonic() + _PORTFOLIO_CACHE_TTL}
    return result


# ── Order execution ───────────────────────────────────────────────────────────

async def place_order(
    ticker: str, side: str, position_size_pct: float, market: str = 'US'
) -> dict:
    """
    Execute a paper trade for the given market.
    position_size_pct: percentage of total portfolio value to allocate.
    Returns an order-result dict compatible with what orchestrator expects.
    """
    if not is_market_open(market):
        raise ValueError(
            f"{market} market is closed — orders only accepted during trading hours"
        )

    _invalidate_portfolio_cache(market)   # stale data the moment a trade starts
    current_price = get_current_price(ticker)

    async with AsyncSessionLocal() as db:
        portfolio = await get_paper_portfolio(db, market)
        from backend.markets import MARKETS
        default_cash = MARKETS.get(market.upper(), MARKETS["US"])["starting_cash"]
        cash = portfolio.cash if portfolio else default_cash
        positions = await get_paper_positions(db, market)

        # Total portfolio value for position sizing
        total_value = cash
        for pos in positions:
            try:
                total_value += pos.qty * get_current_price(pos.ticker)
            except Exception:
                total_value += pos.qty * pos.avg_cost

        notional = round(total_value * (position_size_pct / 100), 2)
        # Round to nearest whole share (minimum 1)
        qty = max(1, round(notional / current_price))

        if side.lower() == "buy":
            if cash < notional:
                raise ValueError(
                    f"Insufficient cash ({cash:,.2f}) for {notional:,.2f} order"
                )
            await update_paper_cash(db, cash - notional, market)

            existing = await get_paper_position(db, ticker, market)
            if existing:
                new_qty = existing.qty + qty
                new_avg = (
                    (existing.qty * existing.avg_cost) + (qty * current_price)
                ) / new_qty
                await upsert_paper_position(db, ticker, new_qty, new_avg, market)
            else:
                await upsert_paper_position(db, ticker, qty, current_price, market)

        else:  # sell
            existing = await get_paper_position(db, ticker, market)
            if not existing:
                raise ValueError(f"No open position in {ticker} to sell")

            sell_qty = min(qty, existing.qty)
            proceeds = round(sell_qty * current_price, 2)
            await update_paper_cash(db, cash + proceeds, market)

            remaining = existing.qty - sell_qty
            if remaining < 0.0001:
                await delete_paper_position(db, ticker, market)
            else:
                await upsert_paper_position(db, ticker, remaining, existing.avg_cost, market)

    return {
        "order_id": f"paper-{uuid.uuid4().hex[:8]}",
        "ticker": ticker,
        "side": side.lower(),
        "qty": qty,
        "price": current_price,
        "notional": notional,
        "status": "filled",
    }
