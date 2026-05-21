from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.session import get_db
from backend.db.crud import get_latest_portfolio_snapshot
from backend.broker.paper_broker import get_portfolio

router = APIRouter()


@router.get("/portfolio")
async def portfolio(db: AsyncSession = Depends(get_db)):
    try:
        live = await get_portfolio()
        positions = live.get("positions", [])
        total_unrealized_pl = round(sum(p.get("unrealized_pl", 0) for p in positions), 2)
        invested = live["total_value"] - live["cash"]
        total_unrealized_pl_pct = (
            round(total_unrealized_pl / invested * 100, 4) if invested > 0 else 0.0
        )
        return {
            "source": "live",
            **live,
            "total_unrealized_pl": total_unrealized_pl,
            "total_unrealized_pl_pct": total_unrealized_pl_pct,
            "position_count": len(positions),
        }
    except Exception as e:
        snapshot = await get_latest_portfolio_snapshot(db)
        if snapshot:
            positions = snapshot.positions or []
            return {
                "source": "snapshot",
                "total_value": snapshot.total_value,
                "cash": snapshot.cash,
                "positions": positions,
                "position_count": len(positions),
                "total_unrealized_pl": None,
                "total_unrealized_pl_pct": None,
            }
        return {"error": str(e)}
