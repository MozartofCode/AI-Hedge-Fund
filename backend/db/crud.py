import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from sqlalchemy.orm import selectinload
from backend.db.models import (
    CommitteeSession, AgentVote, Trade, PortfolioSnapshot,
    PaperPortfolio, PaperPosition,
)

STARTING_CASH = 1_000_000.0


# ── Committee Sessions ────────────────────────────────────────────────────────

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
    session.decision = decision.get("decision")
    session.chairman_rationale = decision.get("chairman_rationale")
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
        filled_at=trade_data.get("filled_at", datetime.utcnow()),
        order_id=trade_data.get("order_id", ""),
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


async def get_recent_sessions(db: AsyncSession, limit: int = 20, offset: int = 0):
    result = await db.execute(
        select(CommitteeSession)
        .options(selectinload(CommitteeSession.agent_votes))
        .order_by(desc(CommitteeSession.session_timestamp))
        .offset(offset)
        .limit(limit)
    )
    return result.scalars().all()


async def get_recent_trades(db: AsyncSession, limit: int = 20, offset: int = 0):
    result = await db.execute(
        select(Trade)
        .order_by(desc(Trade.filled_at), desc(Trade.id))
        .offset(offset)
        .limit(limit)
    )
    return result.scalars().all()


async def get_session_count(db: AsyncSession) -> int:
    result = await db.execute(select(func.count()).select_from(CommitteeSession))
    return result.scalar() or 0


async def get_trade_count(db: AsyncSession) -> int:
    result = await db.execute(select(func.count()).select_from(Trade))
    return result.scalar() or 0


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


async def get_all_portfolio_snapshots(db: AsyncSession) -> list:
    result = await db.execute(
        select(PortfolioSnapshot).order_by(PortfolioSnapshot.snapshot_timestamp)
    )
    return result.scalars().all()


async def compute_win_rate(db: AsyncSession) -> Optional[float]:
    """FIFO-match buy/sell pairs from our own trades table."""
    result = await db.execute(
        select(Trade)
        .where(Trade.filled_price.isnot(None))
        .order_by(Trade.filled_at)
    )
    all_trades = result.scalars().all()

    by_ticker: dict = {}
    for t in all_trades:
        by_ticker.setdefault(t.ticker, []).append(t)

    wins = total = 0
    for ticker_trades in by_ticker.values():
        buys = [t for t in ticker_trades if t.side == "buy" and t.filled_price]
        sells = [t for t in ticker_trades if t.side == "sell" and t.filled_price]
        for sell in sells:
            if buys:
                buy = buys.pop(0)
                if sell.filled_price > buy.filled_price:
                    wins += 1
                total += 1

    return round(wins / total, 4) if total > 0 else None


# ── Paper Trading ─────────────────────────────────────────────────────────────

async def get_paper_portfolio(db: AsyncSession) -> Optional[PaperPortfolio]:
    result = await db.execute(select(PaperPortfolio).where(PaperPortfolio.id == 1))
    return result.scalar_one_or_none()


async def init_paper_portfolio(db: AsyncSession) -> PaperPortfolio:
    portfolio = PaperPortfolio(id=1, cash=STARTING_CASH)
    db.add(portfolio)
    await db.commit()
    await db.refresh(portfolio)
    return portfolio


async def update_paper_cash(db: AsyncSession, new_cash: float) -> None:
    portfolio = await get_paper_portfolio(db)
    if portfolio is None:
        db.add(PaperPortfolio(id=1, cash=new_cash))
    else:
        portfolio.cash = round(new_cash, 2)
        portfolio.updated_at = datetime.utcnow()
    await db.commit()


async def get_paper_positions(db: AsyncSession) -> list:
    result = await db.execute(select(PaperPosition))
    return result.scalars().all()


async def get_paper_position(db: AsyncSession, ticker: str) -> Optional[PaperPosition]:
    result = await db.execute(
        select(PaperPosition).where(PaperPosition.ticker == ticker)
    )
    return result.scalar_one_or_none()


async def upsert_paper_position(
    db: AsyncSession, ticker: str, qty: float, avg_cost: float
) -> None:
    existing = await get_paper_position(db, ticker)
    if existing:
        existing.qty = round(qty, 6)
        existing.avg_cost = round(avg_cost, 4)
        existing.updated_at = datetime.utcnow()
    else:
        db.add(PaperPosition(ticker=ticker, qty=round(qty, 6), avg_cost=round(avg_cost, 4)))
    await db.commit()


async def delete_paper_position(db: AsyncSession, ticker: str) -> None:
    existing = await get_paper_position(db, ticker)
    if existing:
        await db.delete(existing)
        await db.commit()
