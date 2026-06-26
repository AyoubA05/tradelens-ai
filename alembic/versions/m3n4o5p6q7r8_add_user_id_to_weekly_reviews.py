"""add user_id to weekly_reviews (Session D — multi-user weekly coach)

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7
Create Date: 2026-06-26

Adds a nullable user_id column (+ index) to weekly_reviews so AI weekly reviews
are scoped per user. NULL = legacy single-user reviews. Idempotent; the index is
created explicitly inside the migration (index-parity note from Session C).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "m3n4o5p6q7r8"
down_revision: Union[str, Sequence[str], None] = "l2m3n4o5p6q7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_columns(table_name: str) -> set:
    bind = op.get_bind()
    return {c["name"] for c in inspect(bind).get_columns(table_name)}


def _existing_indexes(table_name: str) -> set:
    bind = op.get_bind()
    return {i["name"] for i in inspect(bind).get_indexes(table_name)}


def upgrade() -> None:
    if "user_id" not in _existing_columns("weekly_reviews"):
        op.add_column(
            "weekly_reviews", sa.Column("user_id", sa.Integer(), nullable=True)
        )
    if "ix_weekly_reviews_user_id" not in _existing_indexes("weekly_reviews"):
        op.create_index(
            "ix_weekly_reviews_user_id", "weekly_reviews", ["user_id"]
        )


def downgrade() -> None:
    if "ix_weekly_reviews_user_id" in _existing_indexes("weekly_reviews"):
        op.drop_index("ix_weekly_reviews_user_id", table_name="weekly_reviews")
    if "user_id" in _existing_columns("weekly_reviews"):
        with op.batch_alter_table("weekly_reviews") as batch:
            batch.drop_column("user_id")
