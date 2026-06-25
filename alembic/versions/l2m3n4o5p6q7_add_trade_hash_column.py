"""add trade_hash to trades (Session B — duplicate detection)

Revision ID: l2m3n4o5p6q7
Revises: k1l2m3n4o5p6
Create Date: 2026-06-25

Adds a nullable, indexed trade_hash column used to detect duplicate submissions
and CSV re-imports. Idempotent: skips the column if it already exists.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "l2m3n4o5p6q7"
down_revision: Union[str, Sequence[str], None] = "k1l2m3n4o5p6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_columns(table_name: str) -> set:
    bind = op.get_bind()
    return {c["name"] for c in inspect(bind).get_columns(table_name)}


def upgrade() -> None:
    if "trade_hash" not in _existing_columns("trades"):
        # The index is declared on the model, so fresh DBs (create_all) get it.
        op.add_column("trades", sa.Column("trade_hash", sa.String(), nullable=True))


def downgrade() -> None:
    if "trade_hash" in _existing_columns("trades"):
        with op.batch_alter_table("trades") as batch:
            batch.drop_column("trade_hash")
