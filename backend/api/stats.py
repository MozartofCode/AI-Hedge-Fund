from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import pandas as pd

from backend.db.session import get_db
from backend.db.crud import get_session_count, get_trade_count, get_all_portfolio_snapshots
from backend.broker.alpaca_client import get_portfolio, get_closed_orders

router = APIRouter()


def _win_rate(closed_orders: list) -> Optional[float]:
    """FIFO-match buy/sell pairs per symbol and return fraction that were profitable."""
    by_symbol: dict[str, list] = {}
    for o in closed_orders:
        by_symbol.setdefault(o["symbol"], []).append(o)

    wins = total = 0
    for orders in by_symbol.values():
        buys = [o for o in orders if o["side"] == "buy" and o["filled_avg_price"] > 0]
        sells = [o for o in orders if o["side"] == "sell" and o["filled_avg_price"] > 0]
        for sell in sells:
            if buys:
                buy = buys.pop(0)
                pl = (sell["filled_avg_price"] - buy["filled_avg_price"]) * sell["filled_qty"]
                total += 1
                if pl > 0:
                    wins += 1

    return round(wins / total, 4) if total > 0 else None


def _sharpe(snapshots: list) -> Optional[float]:
    """Annualized Sharpe ratio from portfolio snapshots (risk-free rate = 0)."""
    if len(snapshots) < 2:
        return None
    try:
        series = pd.Series(
            [float(s.total_value) for s in snapshots],
            index=pd.to_datetime([s.snapshot_timestamp for s in snapshots], utc=True),
        )
        daily = series.resample("D").last().dropna()
        returns = daily.pct_change().dropna()
        if len(returns) < 2 or returns.std() == 0:
            return None
        return round(float((returns.mean() / returns.std()) * (252 ** 0.5)), 4)
    except Exception:
        return None


def _equity_curve(snapshots: list) -> list:
    """Daily equity + cumulative P&L from portfolio snapshots."""
    if not snapshots:
        return []
    try:
        series = pd.Series(
            [float(s.total_value) for s in snapshots],
            index=pd.to_datetime([s.snapshot_timestamp for s in snapshots], utc=True),
        )
        daily = series.resample("D").last().dropna()
        base = float(daily.iloc[0])
        return [
            {
                "date": date.strftime("%Y-%m-%d"),
                "equity": round(float(val), 2),
                "pl": round(float(val) - base, 2),
            }
            for date, val in daily.items()
        ]
    except Exception:
        return []


@router.get("/stats")
async def stats(db: AsyncSession = Depends(get_db)):
    # Live portfolio
    total_value = cash = 0.0
    try:
        port = get_portfolio()
        total_value = port["total_value"]
        cash = port["cash"]
    except Exception:
        pass

    # Equity history from our snapshots table
    snapshots = await get_all_portfolio_snapshots(db)

    first_value = float(snapshots[0].total_value) if snapshots else None
    total_pl_usd = round(total_value - first_value, 2) if first_value else None
    total_return_pct = (
        round(total_pl_usd / first_value * 100, 4)
        if first_value and first_value > 0
        else None
    )

    sharpe = _sharpe(snapshots)
    daily_equity = _equity_curve(snapshots)

    # Win rate from Alpaca closed orders
    win_rate = _win_rate(get_closed_orders())

    # DB counts
    total_sessions = await get_session_count(db)
    total_trades = await get_trade_count(db)

    return {
        "total_value": total_value,
        "cash": cash,
        "total_pl_usd": total_pl_usd,
        "total_return_pct": total_return_pct,
        "win_rate": win_rate,
        "sharpe_ratio": sharpe,
        "total_trades": total_trades,
        "total_sessions": total_sessions,
        "daily_equity": daily_equity,
    }
