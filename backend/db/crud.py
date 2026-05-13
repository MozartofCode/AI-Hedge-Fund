import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from sqlalchemy.orm import selectinload
from backend.db.models import CommitteeSession, AgentVote, Trade, PortfolioSnapshot


async def create_session(db: AsyncSession, ticker: str) -> CommitteeSession:
    session = CommitteeSession(ticker=ticker)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def save_agent_vote(db: AsyncSession, session_id: uuid.UUID, vote: dict) -> AgentVote:
    agent_vote = AgentVote(
        session_id=session_id,
        agent_name=vote["agent"],
        action=vote["action"],
        confidence=vote["confidence"],
        rationale=vote["rationale"],
        raw_data_snapshot=vote.get("raw_data"),
    )
    db.add(agent_vote)
    await db.commit()
    await db.refresh(agent_vote)
    return agent_vote


async def finalize_session(db: AsyncSession, session_id: uuid.UUID, decision: dict) -> CommitteeSession:
    result = await db.execute(select(CommitteeSession).where(CommitteeSession.id == session_id))
    session = result.scalar_one()
    session.decision = decision["decision"]
    session.chairman_rationale = decision["chairman_rationale"]
    session.weighted_score = decision.get("weighted_score")
    session.order_placed = decision.get("order_placed", False)
    session.order_id = decision.get("order_id")
    await db.commit()
    await db.refresh(session)
    return session


async def log_trade(db: AsyncSession, session_id: uuid.UUID, trade_data: dict) -> Trade:
    trade = Trade(
        session_id=session_id,
        ticker=trade_data["ticker"],
        side=trade_data["side"],
        qty=trade_data.get("qty", 0),
        filled_price=trade_data.get("filled_price"),
        filled_at=trade_data.get("filled_at"),
        alpaca_order_id=trade_data.get("alpaca_order_id", ""),
    )
    db.add(trade)
    await db.commit()
    await db.refresh(trade)
    return trade


async def save_portfolio_snapshot(db: AsyncSession, snapshot_data: dict) -> PortfolioSnapshot:
    snapshot = PortfolioSnapshot(
        total_value=snapshot_data["total_value"],
        cash=snapshot_data["cash"],
        positions=snapshot_data["positions"],
    )
    db.add(snapshot)
    await db.commit()
    await db.refresh(snapshot)
    return snapshot


async def get_recent_sessions(db: AsyncSession, limit: int = 20):
    result = await db.execute(
        select(CommitteeSession)
        .options(selectinload(CommitteeSession.agent_votes))
        .order_by(desc(CommitteeSession.session_timestamp))
        .limit(limit)
    )
    return result.scalars().all()


async def get_recent_trades(db: AsyncSession, limit: int = 10):
    result = await db.execute(
        select(Trade).order_by(desc(Trade.filled_at)).limit(limit)
    )
    return result.scalars().all()


async def get_latest_portfolio_snapshot(db: AsyncSession):
    result = await db.execute(
        select(PortfolioSnapshot)
        .order_by(desc(PortfolioSnapshot.snapshot_timestamp))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_peak_portfolio_value(db: AsyncSession) -> float:
    result = await db.execute(select(func.max(PortfolioSnapshot.total_value)))
    return result.scalar() or 0.0
