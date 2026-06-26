"""add user_id to trades (Session B — multi-user)

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2026-06-25

Adds a nullable user_id column to trades. NULL = legacy single-user trades,
left untouched. Idempotent: skips the column if it already exists.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "k1l2m3n4o5p6"
down_revision: Union[str, Sequence[str], None] = "j0k1l2m3n4o5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_columns(table_name: str) -> set:
    bind = op.get_bind()
    return {c["name"] for c in inspect(bind).get_columns(table_name)}


def upgrade() -> None:
    if "user_id" not in _existing_columns("trades"):
        # FK + index are declared on the model, so fresh DBs (create_all) get them.
        # SQLite can't ALTER-ADD a foreign key, so the migrated column is plain and
        # the app scopes in Python.
        op.add_column("trades", sa.Column("user_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    if "user_id" in _existing_columns("trades"):
        with op.batch_alter_table("trades") as batch:
            batch.drop_column("user_id")
