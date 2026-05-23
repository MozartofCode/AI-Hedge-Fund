import math
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.session import get_db
from backend.db.crud import (
    get_recent_sessions, get_session_count,
    get_session_by_id, get_latest_session_for_ticker,
)

router = APIRouter()


# ── Factor grade helpers ──────────────────────────────────────────────────────

def _action_score(raw: dict) -> float:
    """Convert action + confidence into a 0–1 bullish score."""
    action = (raw.get("action") or "HOLD").upper()
    conf   = float(raw.get("confidence") or 0.5)
    if action == "BUY":  return conf
    if action == "SELL": return 1.0 - conf
    return 0.5


def _score_to_grade(score) -> str:
    if score is None:
        return "N/A"
    s = float(score)
    if s >= 0.93: return "A+"
    if s >= 0.87: return "A"
    if s >= 0.80: return "A-"
    if s >= 0.77: return "B+"
    if s >= 0.73: return "B"
    if s >= 0.67: return "B-"
    if s >= 0.60: return "C+"
    if s >= 0.53: return "C"
    if s >= 0.47: return "C-"
    if s >= 0.40: return "D+"
    if s >= 0.33: return "D"
    if s >= 0.27: return "D-"
    return "F"


def _compute_factor_grades(agent_votes) -> dict:
    """
    Derive 5 factor letter grades from agent vote raw_data_snapshots.
    Each agent now returns sub-scores; falls back to action/confidence
    for historical sessions that pre-date the sub-score fields.
    """
    raw = {}
    for v in agent_votes:
        snap = v.raw_data_snapshot or {}
        raw[v.agent_name] = snap

    tech_raw  = raw.get("technician",     {})
    fund_raw  = raw.get("fundamentalist", {})
    news_raw  = raw.get("newshound",      {})
    macro_raw = raw.get("macro_watcher",  {})

    momentum = tech_raw.get("momentum_score")
    if momentum is None:
        momentum = _action_score(tech_raw)

    valuation = fund_raw.get("valuation_score")
    if valuation is None:
        valuation = _action_score(fund_raw)

    growth_fund = fund_raw.get("growth_score")
    if growth_fund is None:
        growth_fund = _action_score(fund_raw)
    growth = growth_fund * 0.65 + _action_score(macro_raw) * 0.35

    profitability = fund_raw.get("profitability_score")
    if profitability is None:
        profitability = _action_score(fund_raw)

    revisions = news_raw.get("revisions_score")
    if revisions is None:
        revisions = _action_score(news_raw)

    return {
        "Valuation":     _score_to_grade(valuation),
        "Growth":        _score_to_grade(growth),
        "Profitability": _score_to_grade(profitability),
        "Momentum":      _score_to_grade(momentum),
        "Revisions":     _score_to_grade(revisions),
    }


# ── Shared session serialiser ─────────────────────────────────────────────────

def _serialize_session(s) -> dict:
    factor_grades = _compute_factor_grades(s.agent_votes)
    return {
        "id":                  str(s.id),
        "ticker":              s.ticker,
        "market":              getattr(s, 'market', 'US'),
        "session_timestamp":   s.session_timestamp.isoformat(),
        "decision":            s.decision,
        "chairman_rationale":  s.chairman_rationale,
        "weighted_score":      s.weighted_score,
        "order_placed":        s.order_placed,
        "factor_grades":       factor_grades,
        "agent_votes": [
            {
                "agent_name": v.agent_name,
                "action":     v.action,
                "confidence": v.confidence,
                "rationale":  v.rationale,
                "veto":       v.raw_data_snapshot.get("veto") if v.raw_data_snapshot else None,
            }
            for v in s.agent_votes
        ],
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/session/{session_id}")
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id format")
    s = await get_session_by_id(db, sid)
    if s is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return _serialize_session(s)


@router.get("/latest-session/{ticker}")
async def get_latest_session(
    ticker: str,
    market: str = Query('US'),
    db: AsyncSession = Depends(get_db),
):
    s = await get_latest_session_for_ticker(db, ticker, market.upper())
    if s is None:
        raise HTTPException(status_code=404, detail=f"No session found for {ticker.upper()} in {market.upper()}")
    return _serialize_session(s)


@router.get("/debates")
async def debates(
    page: int = 1,
    limit: int = 20,
    market: str = Query('US'),
    db: AsyncSession = Depends(get_db),
):
    mkt      = market.upper()
    offset   = (page - 1) * limit
    sessions = await get_recent_sessions(db, limit=limit, offset=offset, market=mkt)
    total    = await get_session_count(db, mkt)
    return {
        "market": mkt,
        "items": [
            {
                **_serialize_session(s),
                "order_id": s.order_id,
            }
            for s in sessions
        ],
        "total": total,
        "page":  page,
        "pages": math.ceil(total / limit) if total else 1,
        "limit": limit,
    }
