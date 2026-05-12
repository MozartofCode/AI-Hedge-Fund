from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.session import get_db
from backend.db.crud import get_recent_sessions

router = APIRouter()


@router.get("/debates")
async def debates(limit: int = 20, db: AsyncSession = Depends(get_db)):
    sessions = await get_recent_sessions(db, limit=limit)
    return [
        {
            "id": str(s.id),
            "ticker": s.ticker,
            "session_timestamp": s.session_timestamp.isoformat(),
            "decision": s.decision,
            "chairman_rationale": s.chairman_rationale,
            "weighted_score": s.weighted_score,
            "order_placed": s.order_placed,
            "order_id": s.order_id,
            "agent_votes": [
                {
                    "agent_name": v.agent_name,
                    "action": v.action,
                    "confidence": v.confidence,
                    "rationale": v.rationale,
                }
                for v in s.agent_votes
            ],
        }
        for s in sessions
    ]
