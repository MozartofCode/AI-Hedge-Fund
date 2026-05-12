"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-12

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "committee_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=10), nullable=False),
        sa.Column("session_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision", sa.String(length=10), nullable=True),
        sa.Column("chairman_rationale", sa.Text(), nullable=True),
        sa.Column("weighted_score", sa.Float(), nullable=True),
        sa.Column("order_placed", sa.Boolean(), nullable=True),
        sa.Column("order_id", sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_value", sa.Float(), nullable=True),
        sa.Column("cash", sa.Float(), nullable=True),
        sa.Column(
            "positions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "agent_votes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agent_name", sa.String(length=50), nullable=True),
        sa.Column("action", sa.String(length=10), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column(
            "raw_data_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["committee_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "trades",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ticker", sa.String(length=10), nullable=True),
        sa.Column("side", sa.String(length=10), nullable=True),
        sa.Column("qty", sa.Float(), nullable=True),
        sa.Column("filled_price", sa.Float(), nullable=True),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("alpaca_order_id", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["committee_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("trades")
    op.drop_table("agent_votes")
    op.drop_table("portfolio_snapshots")
    op.drop_table("committee_sessions")
