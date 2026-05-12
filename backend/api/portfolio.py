from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.session import get_db
from backend.db.crud import get_latest_portfolio_snapshot
from backend.broker.alpaca_client import get_portfolio

router = APIRouter()


@router.get("/portfolio")
async def portfolio(db: AsyncSession = Depends(get_db)):
    try:
        live = get_portfolio()
        return {"source": "live", **live}
    except Exception as e:
        snapshot = await get_latest_portfolio_snapshot(db)
        if snapshot:
            return {
                "source": "snapshot",
                "total_value": snapshot.total_value,
                "cash": snapshot.cash,
                "positions": snapshot.positions,
            }
        return {"error": str(e)}
