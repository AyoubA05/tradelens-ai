"""add users table (Session B — multi-user auth)

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-06-25

Creates the users table for bcrypt-backed multi-user login. Idempotent: skips
creation if the table already exists (fresh DBs build it via create_all).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "j0k1l2m3n4o5"
down_revision: Union[str, Sequence[str], None] = "i9j0k1l2m3n4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if "users" not in inspect(bind).get_table_names():
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("username", sa.String(), nullable=False),
            sa.Column("password_hash", sa.String(), nullable=False),
            sa.Column("created_at", sa.String(), nullable=True),
            sa.Column(
                "is_active", sa.Integer(), nullable=False, server_default="1"
            ),
            sa.UniqueConstraint("username", name="uq_users_username"),
        )
        op.create_index("ix_users_username", "users", ["username"])


def downgrade() -> None:
    bind = op.get_bind()
    if "users" in inspect(bind).get_table_names():
        op.drop_table("users")  # SQLite drops the table's indexes with it
