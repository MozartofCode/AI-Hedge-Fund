import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class CommitteeSession(Base):
    __tablename__ = "committee_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker = Column(String(10), nullable=False)
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
    side = Column(String(10))
    qty = Column(Float)
    filled_price = Column(Float, nullable=True)
    filled_at = Column(DateTime(timezone=True), nullable=True)
    alpaca_order_id = Column(String(100))

    session = relationship("CommitteeSession", back_populates="trades")


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_timestamp = Column(DateTime(timezone=True), default=datetime.utcnow)
    total_value = Column(Float)
    cash = Column(Float)
    positions = Column(JSONB)
