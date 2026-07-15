"""add user_id to corrections (multi-user correction memory)

Revision ID: n4o5p6q7r8s9
Revises: m3n4o5p6q7r8
Create Date: 2026-07-03

Adds a nullable user_id column (+ index) to corrections so correction-memory
few-shot blocks, badge counts, and promotion suggestions are scoped per user.
NULL = legacy single-user corrections. Idempotent; index created explicitly.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "n4o5p6q7r8s9"
down_revision: Union[str, Sequence[str], None] = "m3n4o5p6q7r8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_columns(table_name: str) -> set:
    bind = op.get_bind()
    return {c["name"] for c in inspect(bind).get_columns(table_name)}


def _existing_indexes(table_name: str) -> set:
    bind = op.get_bind()
    return {i["name"] for i in inspect(bind).get_indexes(table_name)}


def upgrade() -> None:
    if "user_id" not in _existing_columns("corrections"):
        op.add_column("corrections", sa.Column("user_id", sa.Integer(), nullable=True))
    if "ix_corrections_user_id" not in _existing_indexes("corrections"):
        op.create_index("ix_corrections_user_id", "corrections", ["user_id"])


def downgrade() -> None:
    if "ix_corrections_user_id" in _existing_indexes("corrections"):
        op.drop_index("ix_corrections_user_id", table_name="corrections")
    if "user_id" in _existing_columns("corrections"):
        with op.batch_alter_table("corrections") as batch:
            batch.drop_column("user_id")
