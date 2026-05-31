import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from sqlalchemy.orm import selectinload
from backend.db.models import (
    CommitteeSession, AgentVote, Trade, PortfolioSnapshot,
    PaperPortfolio, PaperPosition,
    ForexPortfolio, ForexPosition,
)


# ── Committee Sessions ────────────────────────────────────────────────────────

async def create_session(db: AsyncSession, ticker: str, market: str = 'US') -> CommitteeSession:
    session = CommitteeSession(ticker=ticker, market=market.upper())
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


async def log_trade(
    db: AsyncSession, session_id: uuid.UUID, trade_data: dict, market: str = 'US'
) -> Trade:
    trade = Trade(
        session_id=session_id,
        ticker=trade_data["ticker"],
        market=market.upper(),
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


async def save_portfolio_snapshot(
    db: AsyncSession, snapshot_data: dict, market: str = 'US'
) -> PortfolioSnapshot:
    snapshot = PortfolioSnapshot(
        market=market.upper(),
        total_value=snapshot_data["total_value"],
        cash=snapshot_data["cash"],
        positions=snapshot_data["positions"],
    )
    db.add(snapshot)
    await db.commit()
    await db.refresh(snapshot)
    return snapshot


async def get_session_by_id(db: AsyncSession, session_id: uuid.UUID):
    result = await db.execute(
        select(CommitteeSession)
        .options(selectinload(CommitteeSession.agent_votes))
        .where(CommitteeSession.id == session_id)
    )
    return result.scalar_one_or_none()


async def get_latest_session_for_ticker(
    db: AsyncSession, ticker: str, market: str = 'US'
):
    result = await db.execute(
        select(CommitteeSession)
        .options(selectinload(CommitteeSession.agent_votes))
        .where(
            CommitteeSession.ticker == ticker.upper(),
            CommitteeSession.market == market.upper(),
        )
        .order_by(desc(CommitteeSession.session_timestamp))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_recent_sessions(
    db: AsyncSession, limit: int = 20, offset: int = 0, market: str = 'US'
):
    result = await db.execute(
        select(CommitteeSession)
        .options(selectinload(CommitteeSession.agent_votes))
        .where(CommitteeSession.market == market.upper())
        .order_by(desc(CommitteeSession.session_timestamp))
        .offset(offset)
        .limit(limit)
    )
    return result.scalars().all()


async def get_recent_trades(
    db: AsyncSession, limit: int = 20, offset: int = 0, market: str = 'US'
):
    result = await db.execute(
        select(Trade)
        .where(Trade.market == market.upper())
        .order_by(desc(Trade.filled_at), desc(Trade.id))
        .offset(offset)
        .limit(limit)
    )
    return result.scalars().all()


async def get_session_count(db: AsyncSession, market: str = 'US') -> int:
    result = await db.execute(
        select(func.count())
        .select_from(CommitteeSession)
        .where(CommitteeSession.market == market.upper())
    )
    return result.scalar() or 0


async def get_trade_count(db: AsyncSession, market: str = 'US') -> int:
    result = await db.execute(
        select(func.count())
        .select_from(Trade)
        .where(Trade.market == market.upper())
    )
    return result.scalar() or 0


async def get_latest_portfolio_snapshot(db: AsyncSession, market: str = 'US'):
    result = await db.execute(
        select(PortfolioSnapshot)
        .where(PortfolioSnapshot.market == market.upper())
        .order_by(desc(PortfolioSnapshot.snapshot_timestamp))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_peak_portfolio_value(db: AsyncSession, market: str = 'US') -> float:
    result = await db.execute(
        select(func.max(PortfolioSnapshot.total_value))
        .where(PortfolioSnapshot.market == market.upper())
    )
    return result.scalar() or 0.0


async def get_all_portfolio_snapshots(db: AsyncSession, market: str = 'US') -> list:
    result = await db.execute(
        select(PortfolioSnapshot)
        .where(PortfolioSnapshot.market == market.upper())
        .order_by(PortfolioSnapshot.snapshot_timestamp)
    )
    return result.scalars().all()


async def compute_win_rate(db: AsyncSession, market: str = 'US') -> Optional[float]:
    """FIFO-match buy/sell pairs from our own trades table for a given market."""
    result = await db.execute(
        select(Trade)
        .where(Trade.market == market.upper(), Trade.filled_price.isnot(None))
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

# Stable integer PKs per market — avoids relying on the DB sequence, which may
# not exist if the table was originally created with a literal DEFAULT 1.
_MARKET_PK = {'US': 1, 'BR': 2, 'AR': 3, 'TR': 4, 'NG': 5}


async def get_paper_portfolio(
    db: AsyncSession, market: str = 'US'
) -> Optional[PaperPortfolio]:
    result = await db.execute(
        select(PaperPortfolio).where(PaperPortfolio.market_code == market.upper())
    )
    return result.scalar_one_or_none()


async def init_paper_portfolio(
    db: AsyncSession, market: str = 'US', starting_cash: float = 1_000_000.0
) -> PaperPortfolio:
    """Idempotent: only seed the row if it doesn't exist yet for this market."""
    mkt = market.upper()
    existing = await get_paper_portfolio(db, mkt)
    if existing is not None:
        return existing
    # Use a deterministic integer PK so we never rely on the column's DEFAULT
    # (the old schema used a literal DEFAULT 1, leaving no real sequence).
    pk = _MARKET_PK.get(mkt, 100 + abs(hash(mkt)) % 900)
    portfolio = PaperPortfolio(id=pk, market_code=mkt, cash=starting_cash)
    db.add(portfolio)
    await db.commit()
    await db.refresh(portfolio)
    return portfolio


async def update_paper_cash(
    db: AsyncSession, new_cash: float, market: str = 'US'
) -> None:
    portfolio = await get_paper_portfolio(db, market)
    if portfolio is None:
        db.add(PaperPortfolio(market_code=market.upper(), cash=new_cash))
    else:
        portfolio.cash = round(new_cash, 2)
        portfolio.updated_at = datetime.utcnow()
    await db.commit()


async def get_paper_positions(db: AsyncSession, market: str = 'US') -> list:
    result = await db.execute(
        select(PaperPosition).where(PaperPosition.market == market.upper())
    )
    return result.scalars().all()


async def get_paper_position(
    db: AsyncSession, ticker: str, market: str = 'US'
) -> Optional[PaperPosition]:
    result = await db.execute(
        select(PaperPosition).where(
            PaperPosition.ticker == ticker,
            PaperPosition.market == market.upper(),
        )
    )
    return result.scalar_one_or_none()


async def upsert_paper_position(
    db: AsyncSession, ticker: str, qty: float, avg_cost: float, market: str = 'US'
) -> None:
    existing = await get_paper_position(db, ticker, market)
    if existing:
        existing.qty = round(qty, 6)
        existing.avg_cost = round(avg_cost, 4)
        existing.updated_at = datetime.utcnow()
    else:
        db.add(PaperPosition(
            ticker=ticker,
            market=market.upper(),
            qty=round(qty, 6),
            avg_cost=round(avg_cost, 4),
        ))
    await db.commit()


async def delete_paper_position(
    db: AsyncSession, ticker: str, market: str = 'US'
) -> None:
    existing = await get_paper_position(db, ticker, market)
    if existing:
        await db.delete(existing)
        await db.commit()


# ── Forex Paper Trading ───────────────────────────────────────────────────────

async def get_forex_portfolio(db: AsyncSession) -> Optional[ForexPortfolio]:
    result = await db.execute(select(ForexPortfolio).where(ForexPortfolio.id == 1))
    return result.scalar_one_or_none()


async def init_forex_portfolio(
    db: AsyncSession, starting_cash: float = 1_000_000.0
) -> ForexPortfolio:
    """Idempotent — only seeds the row if it doesn't exist yet."""
    existing = await get_forex_portfolio(db)
    if existing is not None:
        return existing
    portfolio = ForexPortfolio(id=1, cash=starting_cash)
    db.add(portfolio)
    await db.commit()
    await db.refresh(portfolio)
    return portfolio


async def update_forex_cash(db: AsyncSession, new_cash: float) -> None:
    portfolio = await get_forex_portfolio(db)
    if portfolio is None:
        db.add(ForexPortfolio(id=1, cash=round(new_cash, 2)))
    else:
        portfolio.cash = round(new_cash, 2)
        portfolio.updated_at = datetime.utcnow()
    await db.commit()


async def get_forex_positions(db: AsyncSession) -> list:
    result = await db.execute(select(ForexPosition))
    return result.scalars().all()


async def get_forex_position(
    db: AsyncSession, pair: str
) -> Optional[ForexPosition]:
    result = await db.execute(
        select(ForexPosition).where(ForexPosition.pair == pair.upper())
    )
    return result.scalar_one_or_none()


async def upsert_forex_position(
    db: AsyncSession,
    pair: str,
    direction: str,
    notional_usd: float,
    entry_rate: float,
    stop_loss_rate: float = None,
) -> None:
    existing = await get_forex_position(db, pair)
    if existing:
        existing.direction      = direction
        existing.notional_usd   = round(notional_usd, 2)
        existing.entry_rate     = round(entry_rate, 6)
        existing.stop_loss_rate = round(stop_loss_rate, 6) if stop_loss_rate else None
        existing.updated_at     = datetime.utcnow()
    else:
        db.add(ForexPosition(
            pair=pair.upper(),
            direction=direction,
            notional_usd=round(notional_usd, 2),
            entry_rate=round(entry_rate, 6),
            stop_loss_rate=round(stop_loss_rate, 6) if stop_loss_rate else None,
        ))
    await db.commit()


async def delete_forex_position(db: AsyncSession, pair: str) -> None:
    existing = await get_forex_position(db, pair)
    if existing:
        await db.delete(existing)
        await db.commit()


async def compute_forex_win_rate(db: AsyncSession) -> Optional[float]:
    """Match long_open/long_close and short_open/short_close pairs from the Trade table."""
    result = await db.execute(
        select(Trade)
        .where(Trade.market == "FOREX", Trade.filled_price.isnot(None))
        .order_by(Trade.filled_at)
    )
    all_trades = result.scalars().all()

    by_pair: dict = {}
    for t in all_trades:
        by_pair.setdefault(t.ticker, []).append(t)

    wins = total = 0
    for pair_trades in by_pair.values():
        entries = [t for t in pair_trades if t.side in ("buy", "sell_short") and t.filled_price]
        exits   = [t for t in pair_trades if t.side in ("sell", "buy_cover")  and t.filled_price]
        for exit_trade in exits:
            if entries:
                entry = entries.pop(0)
                if exit_trade.side == "sell" and exit_trade.filled_price > entry.filled_price:
                    wins += 1
                elif exit_trade.side == "buy_cover" and exit_trade.filled_price < entry.filled_price:
                    wins += 1
                total += 1

    return round(wins / total, 4) if total > 0 else None
