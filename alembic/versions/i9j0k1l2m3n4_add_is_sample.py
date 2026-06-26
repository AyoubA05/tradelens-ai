"""add is_sample flag to trades (Session A)

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-06-24

Adds a nullable is_sample integer flag so demo/sample trades can be cleared
without touching real trades. Idempotent: skips the column if it already exists.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "i9j0k1l2m3n4"
down_revision: Union[str, Sequence[str], None] = "h8i9j0k1l2m3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_columns(table_name: str) -> set:
    bind = op.get_bind()
    return {c["name"] for c in inspect(bind).get_columns(table_name)}


def upgrade() -> None:
    if "is_sample" not in _existing_columns("trades"):
        op.add_column(
            "trades",
            sa.Column("is_sample", sa.Integer(), nullable=True, server_default="0"),
        )


def downgrade() -> None:
    if "is_sample" in _existing_columns("trades"):
        with op.batch_alter_table("trades") as batch:
            batch.drop_column("is_sample")
