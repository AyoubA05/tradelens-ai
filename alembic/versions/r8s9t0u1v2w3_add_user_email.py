"""add optional email to users

Revision ID: r8s9t0u1v2w3
Revises: q7r8s9t0u1v2
Create Date: 2026-07-25

Accounts had no contact field at all, which made a forgotten password an
unrecoverable account. The column is nullable so existing accounts stay
valid without one, and unique so an address identifies exactly one account
during password reset. Both SQLite and PostgreSQL permit repeated NULLs
under a unique index, so "optional" and "unique" coexist.

Batch mode is used so SQLite can add the column and its index by table
rebuild. Both directions are guarded so a partially-applied database
converges rather than erroring.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "r8s9t0u1v2w3"
down_revision: Union[str, Sequence[str], None] = "q7r8s9t0u1v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

USERS_EMAIL_INDEX = "ix_users_email"


def _existing_tables() -> set:
    return set(inspect(op.get_bind()).get_table_names())


def _existing_columns(table_name: str) -> set:
    return {column["name"] for column in inspect(op.get_bind()).get_columns(table_name)}


def _existing_indexes(table_name: str) -> set:
    return {index["name"] for index in inspect(op.get_bind()).get_indexes(table_name)}


def upgrade() -> None:
    if "users" not in _existing_tables():
        return

    columns = _existing_columns("users")
    indexes = _existing_indexes("users")

    if "email" not in columns:
        with op.batch_alter_table("users") as batch:
            batch.add_column(sa.Column("email", sa.String(), nullable=True))
        indexes = _existing_indexes("users")

    if USERS_EMAIL_INDEX not in indexes:
        op.create_index(USERS_EMAIL_INDEX, "users", ["email"], unique=True)


def downgrade() -> None:
    if "users" not in _existing_tables():
        return

    if USERS_EMAIL_INDEX in _existing_indexes("users"):
        op.drop_index(USERS_EMAIL_INDEX, table_name="users")

    if "email" in _existing_columns("users"):
        with op.batch_alter_table("users") as batch:
            batch.drop_column("email")
