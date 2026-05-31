import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, Boolean, DateTime, Text, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class CommitteeSession(Base):
    __tablename__ = "committee_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker = Column(String(10), nullable=False)
    market = Column(String(5), nullable=False, default='US')
    session_timestamp = Column(DateTime(timezone=True), default=datetime.utcnow)
    decision = Column(String(10))
    chairman_rationale = Column(Text)
    weighted_score = Column(Float)
    order_placed = Column(Boolean, default=False)
    order_id = Column(String(100))

    agent_votes = relationship("AgentVote", back_populates="session")
    trades = relationship("Trade", back_populates="session")


class AgentVote(Base):
    __tablename__ = "agent_votes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("committee_sessions.id"))
    agent_name = Column(String(50))
    action = Column(String(10))
    confidence = Column(Float)
    rationale = Column(Text)
    raw_data_snapshot = Column(JSONB)

    session = relationship("CommitteeSession", back_populates="agent_votes")


class Trade(Base):
    __tablename__ = "trades"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("committee_sessions.id"), nullable=True)
    ticker = Column(String(10))
    market = Column(String(5), nullable=False, default='US')
    side = Column(String(10))
    qty = Column(Float)
    filled_price = Column(Float, nullable=True)
    filled_at = Column(DateTime(timezone=True), nullable=True)
    order_id = Column(String(100))

    session = relationship("CommitteeSession", back_populates="trades")


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    market = Column(String(5), nullable=False, default='US')
    snapshot_timestamp = Column(DateTime(timezone=True), default=datetime.utcnow)
    total_value = Column(Float)
    cash = Column(Float)
    positions = Column(JSONB)


# ── Paper Trading Tables ──────────────────────────────────────────────────────

class PaperPortfolio(Base):
    """One row per market — tracks paper trading cash balance per exchange."""
    __tablename__ = "paper_portfolio"

    id = Column(Integer, primary_key=True, autoincrement=True)
    market_code = Column(String(5), nullable=False, unique=True, default='US')
    cash = Column(Float, nullable=False, default=1_000_000.0)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class PaperPosition(Base):
    """One row per open ticker+market position."""
    __tablename__ = "paper_positions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker = Column(String(10), nullable=False)
    market = Column(String(5), nullable=False, default='US')
    qty = Column(Float, nullable=False)
    avg_cost = Column(Float, nullable=False)   # average purchase price per share
    opened_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)


# ── Forex Paper Trading Tables ────────────────────────────────────────────────

class ForexPortfolio(Base):
    """Single-row forex paper account — $1M USD starting balance."""
    __tablename__ = "forex_portfolio"

    id         = Column(Integer, primary_key=True)   # always 1
    cash       = Column(Float, nullable=False, default=1_000_000.0)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class ForexPosition(Base):
    """One row per open currency pair — long OR short."""
    __tablename__ = "forex_positions"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pair           = Column(String(10), nullable=False, unique=True)  # e.g. "EURUSD"
    direction      = Column(String(5), nullable=False)                # "long" | "short"
    notional_usd   = Column(Float, nullable=False)                    # USD amount invested
    entry_rate     = Column(Float, nullable=False)                    # exchange rate at entry
    stop_loss_rate = Column(Float, nullable=True)                     # rate to auto-close
    opened_at      = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at     = Column(DateTime(timezone=True), default=datetime.utcnow)
