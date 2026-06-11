"""add aianalysis table

Revision ID: a1b2c3d4e5f6
Revises: 8383cf3ef6e7
Create Date: 2026-06-06 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "8383cf3ef6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "aianalysis",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trade_id", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("prompt_version", sa.String(), nullable=True),
        sa.Column("bias", sa.String(), nullable=True),
        sa.Column("detected_setup", sa.String(), nullable=True),
        sa.Column("zones_json", sa.Text(), nullable=True),
        sa.Column("matched_strategy", sa.String(), nullable=True),
        sa.Column("mistakes_json", sa.Text(), nullable=True),
        sa.Column("missed_opps_json", sa.Text(), nullable=True),
        sa.Column("trade_quality", sa.Integer(), nullable=True),
        sa.Column("journal_entry_md", sa.Text(), nullable=True),
        sa.Column("raw_response_json", sa.Text(), nullable=True),
        sa.Column("tokens_input", sa.Integer(), nullable=True),
        sa.Column("tokens_output", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=True),
        sa.Column("updated_at", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["trade_id"], ["trades.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trade_id", name="uq_aianalysis_trade_id"),
    )
    op.create_index("ix_aianalysis_id", "aianalysis", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_aianalysis_id", table_name="aianalysis")
    op.drop_table("aianalysis")
