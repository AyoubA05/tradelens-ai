"""add weekly_reviews table (Phase 4)

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-06-19

Creates the weekly_reviews table that persists generated weekly AI reviews.
Idempotent: skips creation if the table already exists; downgrade drops it.

A whole-table create/drop is natively reversible on SQLite, so no
batch_alter_table is required here (that pattern is only needed for column
ALTERs on existing tables).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "h8i9j0k1l2m3"
down_revision: Union[str, Sequence[str], None] = "g7h8i9j0k1l2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _table_exists("weekly_reviews"):
        return
    op.create_table(
        "weekly_reviews",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("week_start", sa.String(), nullable=False, index=True),
        sa.Column("content_md", sa.Text(), nullable=True),
        sa.Column("thinking_summary", sa.Text(), nullable=True),
        sa.Column("stats_json", sa.Text(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=True),
    )


def downgrade() -> None:
    if _table_exists("weekly_reviews"):
        op.drop_table("weekly_reviews")
