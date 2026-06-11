"""add corrections table

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-09 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "corrections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trade_id", sa.Integer(), sa.ForeignKey("trades.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ai_analysis_id", sa.Integer(), sa.ForeignKey("aianalysis.id", ondelete="CASCADE"), nullable=False),
        sa.Column("field", sa.Text(), nullable=False),
        sa.Column("ai_value", sa.Text(), nullable=True),
        sa.Column("user_value", sa.Text(), nullable=True),
        sa.Column("user_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("corrections")
