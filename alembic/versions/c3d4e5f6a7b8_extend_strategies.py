"""extend strategies with full blueprint schema

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-07 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("strategies", sa.Column("markets", sa.Text(), nullable=True))
    op.add_column("strategies", sa.Column("timeframes", sa.Text(), nullable=True))
    op.add_column("strategies", sa.Column("stop_rules", sa.Text(), nullable=True))
    op.add_column("strategies", sa.Column("take_profit_rules", sa.Text(), nullable=True))
    op.add_column("strategies", sa.Column("risk_rules", sa.Text(), nullable=True))
    op.add_column("strategies", sa.Column("setups_traded", sa.Text(), nullable=True))
    op.add_column("strategies", sa.Column("setups_avoided", sa.Text(), nullable=True))
    op.add_column("strategies", sa.Column("news_session_rules", sa.Text(), nullable=True))
    op.add_column("strategies", sa.Column("common_mistakes", sa.Text(), nullable=True))
    op.add_column("strategies", sa.Column("is_active", sa.Integer(), nullable=True))
    op.add_column("strategies", sa.Column("created_at", sa.String(), nullable=True))
    op.add_column("strategies", sa.Column("updated_at", sa.String(), nullable=True))

    # Backfill existing rows: set is_active = 0 so no row is left in ambiguous NULL state
    op.execute("UPDATE strategies SET is_active = 0 WHERE is_active IS NULL")


def downgrade() -> None:
    op.drop_column("strategies", "updated_at")
    op.drop_column("strategies", "created_at")
    op.drop_column("strategies", "is_active")
    op.drop_column("strategies", "common_mistakes")
    op.drop_column("strategies", "news_session_rules")
    op.drop_column("strategies", "setups_avoided")
    op.drop_column("strategies", "setups_traded")
    op.drop_column("strategies", "risk_rules")
    op.drop_column("strategies", "take_profit_rules")
    op.drop_column("strategies", "stop_rules")
    op.drop_column("strategies", "timeframes")
    op.drop_column("strategies", "markets")
