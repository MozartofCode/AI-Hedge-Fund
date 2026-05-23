from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
import pandas as pd

from backend.db.session import get_db
from backend.db.crud import (
    get_session_count, get_trade_count,
    get_all_portfolio_snapshots, compute_win_rate,
)
from backend.broker.paper_broker import get_portfolio

router = APIRouter()


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
async def stats(market: str = Query('US'), db: AsyncSession = Depends(get_db)):
    mkt = market.upper()

    # Live portfolio
    total_value = cash = 0.0
    try:
        port = await get_portfolio(mkt)
        total_value = port["total_value"]
        cash = port["cash"]
    except Exception:
        pass

    # Equity history from snapshots table
    snapshots = await get_all_portfolio_snapshots(db, mkt)

    first_value = float(snapshots[0].total_value) if snapshots else None
    total_pl_usd = round(total_value - first_value, 2) if first_value else None
    total_return_pct = (
        round(total_pl_usd / first_value * 100, 4)
        if first_value and first_value > 0
        else None
    )

    sharpe = _sharpe(snapshots)
    daily_equity = _equity_curve(snapshots)

    win_rate = await compute_win_rate(db, mkt)
    total_sessions = await get_session_count(db, mkt)
    total_trades = await get_trade_count(db, mkt)

    return {
        "market": mkt,
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
