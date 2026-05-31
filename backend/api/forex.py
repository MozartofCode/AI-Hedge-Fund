"""
Forex API routes — mirrors the structure of api/portfolio.py + api/stats.py.
All routes prefixed with /api/forex when registered in main.py.
"""
import pandas as pd
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import get_db
from backend.db.crud import (
    get_recent_trades, get_trade_count,
    get_all_portfolio_snapshots, compute_forex_win_rate,
)
from backend.broker.forex_broker import get_portfolio as get_forex_portfolio_data
from backend.data.forex_client import get_all_current_rates, FOREX_PAIRS, CENTRAL_BANK_RATES, parse_pair_currencies

router = APIRouter()


# ── GET /api/forex/portfolio ──────────────────────────────────────────────────

@router.get("/forex/portfolio")
async def forex_portfolio():
    """Live positions + unrealized P&L. No DB needed — broker fetches live rates."""
    try:
        data = await get_forex_portfolio_data()
        return {
            "source":    "live",
            "total_value":  data["total_value"],
            "cash":         data["cash"],
            "buying_power": data["buying_power"],
            "positions":    data["positions"],
            "position_count": len(data["positions"]),
            "total_unrealized_pl": round(
                sum(p["unrealized_pl"] for p in data["positions"]), 2
            ),
        }
    except Exception as e:
        return {"error": str(e), "total_value": 1_000_000.0, "cash": 1_000_000.0, "positions": []}


# ── GET /api/forex/stats ──────────────────────────────────────────────────────

def _sharpe(snapshots) -> Optional[float]:
    if len(snapshots) < 2:
        return None
    try:
        series  = pd.Series(
            [float(s.total_value) for s in snapshots],
            index=pd.to_datetime([s.snapshot_timestamp for s in snapshots], utc=True),
        )
        daily   = series.resample("D").last().dropna()
        returns = daily.pct_change().dropna()
        if len(returns) < 2 or returns.std() == 0:
            return None
        return round(float((returns.mean() / returns.std()) * (252 ** 0.5)), 4)
    except Exception:
        return None


def _equity_curve(snapshots) -> list:
    if not snapshots:
        return []
    try:
        series = pd.Series(
            [float(s.total_value) for s in snapshots],
            index=pd.to_datetime([s.snapshot_timestamp for s in snapshots], utc=True),
        )
        daily = series.resample("D").last().dropna()
        base  = float(daily.iloc[0])
        return [
            {"date": d.strftime("%Y-%m-%d"), "equity": round(float(v), 2), "pl": round(float(v) - base, 2)}
            for d, v in daily.items()
        ]
    except Exception:
        return []


@router.get("/forex/stats")
async def forex_stats(db: AsyncSession = Depends(get_db)):
    """Portfolio statistics — mirrors /api/stats but for FOREX market."""
    total_value = cash = 0.0
    try:
        port = await get_forex_portfolio_data()
        total_value = port["total_value"]
        cash        = port["cash"]
    except Exception:
        pass

    snapshots    = await get_all_portfolio_snapshots(db, "FOREX")
    first_value  = float(snapshots[0].total_value) if snapshots else None
    total_pl     = round(total_value - first_value, 2) if first_value else None
    return_pct   = (
        round(total_pl / first_value * 100, 4) if first_value and first_value > 0 else None
    )

    win_rate      = await compute_forex_win_rate(db)
    total_trades  = await get_trade_count(db, "FOREX")
    sharpe        = _sharpe(snapshots)
    daily_equity  = _equity_curve(snapshots)

    return {
        "total_value":      total_value,
        "cash":             cash,
        "total_pl_usd":     total_pl,
        "total_return_pct": return_pct,
        "win_rate":         win_rate,
        "sharpe_ratio":     sharpe,
        "total_trades":     total_trades,
        "daily_equity":     daily_equity,
    }


# ── GET /api/forex/trades ─────────────────────────────────────────────────────

@router.get("/forex/trades")
async def forex_trades(
    page:  int = Query(1,  ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Paginated forex trade history. Reuses get_recent_trades(market='FOREX')."""
    offset = (page - 1) * limit
    trades = await get_recent_trades(db, limit=limit, offset=offset, market="FOREX")
    total  = await get_trade_count(db, "FOREX")
    return {
        "items": [
            {
                "id":           str(t.id),
                "pair":         t.ticker,   # stored in ticker column
                "side":         t.side,
                "filled_price": t.filled_price,
                "notional_usd": t.qty,      # stored in qty column
                "filled_at":    t.filled_at.isoformat() if t.filled_at else None,
                "order_id":     t.order_id,
            }
            for t in trades
        ],
        "total": total,
        "page":  page,
        "pages": max(1, -(-total // limit)),   # ceiling division
    }


# ── GET /api/forex/rates ──────────────────────────────────────────────────────

@router.get("/forex/rates")
async def forex_rates():
    """Current live rates for all 10 pairs + carry differential."""
    try:
        rates = get_all_current_rates()
    except Exception:
        rates = {}

    result = []
    for pair in FOREX_PAIRS:
        rate = rates.get(pair)
        base, quote = parse_pair_currencies(pair)
        carry = round(
            CENTRAL_BANK_RATES.get(base, 0) - CENTRAL_BANK_RATES.get(quote, 0), 2
        )
        result.append({
            "pair":               pair,
            "rate":               rate,
            "base_currency":      base,
            "quote_currency":     quote,
            "carry_differential": carry,
        })

    return {"rates": result, "pairs": FOREX_PAIRS}


# ── POST /api/forex/run-committee ────────────────────────────────────────────

@router.post("/forex/run-committee")
async def forex_run_committee(pair: str = Query(None)):
    """Run committee for one pair or all pairs."""
    try:
        from backend.forex_orchestrator import run_committee_for_pair, run_full_forex_committee
        from backend.broker.forex_broker import get_portfolio
        from backend.db.session import AsyncSessionLocal
        from backend.db.crud import get_peak_portfolio_value

        if pair:
            portfolio = await get_portfolio()
            async with AsyncSessionLocal() as db:
                peak = await get_peak_portfolio_value(db, "FOREX")
            peak = max(peak, portfolio["total_value"])
            result = await run_committee_for_pair(pair.upper(), portfolio, peak)
            return result
        else:
            results = await run_full_forex_committee()
            return {"results": results, "count": len(results)}
    except Exception as e:
        return {"error": str(e)}
