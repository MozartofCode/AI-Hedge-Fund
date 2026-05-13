import math
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.session import get_db
from backend.db.crud import get_recent_trades, get_trade_count

router = APIRouter()


@router.get("/trades")
async def trades(page: int = 1, limit: int = 20, db: AsyncSession = Depends(get_db)):
    offset = (page - 1) * limit
    rows = await get_recent_trades(db, limit=limit, offset=offset)
    total = await get_trade_count(db)
    return {
        "items": [
            {
                "id": str(t.id),
                "ticker": t.ticker,
                "side": t.side,
                "qty": t.qty,
                "filled_price": t.filled_price,
                "filled_at": t.filled_at.isoformat() if t.filled_at else None,
                "alpaca_order_id": t.alpaca_order_id,
                "session_id": str(t.session_id) if t.session_id else None,
            }
            for t in rows
        ],
        "total": total,
        "page": page,
        "pages": math.ceil(total / limit) if total else 1,
        "limit": limit,
    }
