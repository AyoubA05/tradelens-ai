"""add ai_usage_log table (cost telemetry completeness)

Revision ID: o5p6q7r8s9t0
Revises: n4o5p6q7r8s9
Create Date: 2026-07-03

Per-call AI usage rows for features that have no natural persistence row
(AI Partner chat, pattern-card detection), so the Settings cost dashboard
reflects real spend. Idempotent; downgrade drops the table.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "o5p6q7r8s9t0"
down_revision: Union[str, Sequence[str], None] = "n4o5p6q7r8s9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_tables() -> set:
    bind = op.get_bind()
    return set(inspect(bind).get_table_names())


def upgrade() -> None:
    if "ai_usage_log" in _existing_tables():
        return
    op.create_table(
        "ai_usage_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("feature", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("tokens_input", sa.Integer(), nullable=True),
        sa.Column("tokens_output", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=True),
    )
    op.create_index("ix_ai_usage_log_user_id", "ai_usage_log", ["user_id"])


def downgrade() -> None:
    if "ai_usage_log" in _existing_tables():
        op.drop_table("ai_usage_log")
