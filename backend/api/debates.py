import math
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.session import get_db
from backend.db.crud import get_recent_sessions, get_session_count, get_session_by_id

router = APIRouter()


@router.get("/session/{session_id}")
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id format")
    s = await get_session_by_id(db, sid)
    if s is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "id": str(s.id),
        "ticker": s.ticker,
        "session_timestamp": s.session_timestamp.isoformat(),
        "decision": s.decision,
        "chairman_rationale": s.chairman_rationale,
        "weighted_score": s.weighted_score,
        "order_placed": s.order_placed,
        "agent_votes": [
            {
                "agent_name": v.agent_name,
                "action": v.action,
                "confidence": v.confidence,
                "rationale": v.rationale,
                "veto": v.raw_data_snapshot.get("veto") if v.raw_data_snapshot else None,
            }
            for v in s.agent_votes
        ],
    }


@router.get("/debates")
async def debates(page: int = 1, limit: int = 20, db: AsyncSession = Depends(get_db)):
    offset = (page - 1) * limit
    sessions = await get_recent_sessions(db, limit=limit, offset=offset)
    total = await get_session_count(db)
    return {
        "items": [
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
                        "veto": v.raw_data_snapshot.get("veto") if v.raw_data_snapshot else None,
                    }
                    for v in s.agent_votes
                ],
            }
            for s in sessions
        ],
        "total": total,
        "page": page,
        "pages": math.ceil(total / limit) if total else 1,
        "limit": limit,
    }
