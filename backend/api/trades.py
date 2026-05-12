from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.session import get_db
from backend.db.crud import get_recent_trades

router = APIRouter()


@router.get("/trades")
async def trades(limit: int = 10, db: AsyncSession = Depends(get_db)):
    rows = await get_recent_trades(db, limit=limit)
    return [
        {
            "id": str(t.id),
            "ticker": t.ticker,
            "side": t.side,
            "qty": t.qty,
            "filled_price": t.filled_price,
            "filled_at": t.filled_at.isoformat() if t.filled_at else None,
            "alpaca_order_id": t.alpaca_order_id,
        }
        for t in rows
    ]
