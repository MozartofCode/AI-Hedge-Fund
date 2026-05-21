"""paper trading tables + rename alpaca_order_id

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-20

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rename alpaca_order_id -> order_id on trades table
    op.alter_column("trades", "alpaca_order_id", new_column_name="order_id")

    # Paper portfolio: single-row cash balance
    op.create_table(
        "paper_portfolio",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cash", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Paper positions: one row per open ticker
    op.create_table(
        "paper_positions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=10), nullable=False),
        sa.Column("qty", sa.Float(), nullable=False),
        sa.Column("avg_cost", sa.Float(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticker"),
    )


def downgrade() -> None:
    op.drop_table("paper_positions")
    op.drop_table("paper_portfolio")
    op.alter_column("trades", "order_id", new_column_name="alpaca_order_id")
