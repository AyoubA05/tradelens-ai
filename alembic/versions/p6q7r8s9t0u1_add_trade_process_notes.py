"""add trade_process_notes to trades (Item 8 — Psychology process notes)

Revision ID: p6q7r8s9t0u1
Revises: o5p6q7r8s9t0
Create Date: 2026-07-04

Adds a nullable text column for "What happened during this trade?" — mechanical
process notes (what the chart did, what the trader did), separate from the
emotional mindset fields. Idempotent; downgrade drops the column.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "p6q7r8s9t0u1"
down_revision: Union[str, Sequence[str], None] = "o5p6q7r8s9t0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_columns(table_name: str) -> set:
    bind = op.get_bind()
    return {c["name"] for c in inspect(bind).get_columns(table_name)}


def upgrade() -> None:
    if "trade_process_notes" not in _existing_columns("trades"):
        op.add_column(
            "trades", sa.Column("trade_process_notes", sa.Text(), nullable=True)
        )


def downgrade() -> None:
    if "trade_process_notes" in _existing_columns("trades"):
        with op.batch_alter_table("trades") as batch:
            batch.drop_column("trade_process_notes")
