"""add user-owned strategies and settings

Revision ID: q7r8s9t0u1v2
Revises: p6q7r8s9t0u1
Create Date: 2026-07-22

Adds nullable ownership for legacy strategies and per-user key/value settings.
The strategy alteration uses Alembic batch mode so SQLite can add and remove
the foreign-key constraint during upgrade and downgrade.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision: str = "q7r8s9t0u1v2"
down_revision: Union[str, Sequence[str], None] = "p6q7r8s9t0u1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STRATEGY_USER_FK = "fk_strategies_user_id_users"
STRATEGY_USER_INDEX = "ix_strategies_user_id"


def _existing_tables() -> set:
    return set(inspect(op.get_bind()).get_table_names())


def _existing_columns(table_name: str) -> set:
    return {column["name"] for column in inspect(op.get_bind()).get_columns(table_name)}


def _existing_indexes(table_name: str) -> set:
    return {index["name"] for index in inspect(op.get_bind()).get_indexes(table_name)}


def _existing_foreign_keys(table_name: str) -> set:
    return {
        foreign_key["name"]
        for foreign_key in inspect(op.get_bind()).get_foreign_keys(table_name)
    }


def upgrade() -> None:
    if "strategies" in _existing_tables():
        strategy_columns = _existing_columns("strategies")
        strategy_foreign_keys = _existing_foreign_keys("strategies")
        if (
            "user_id" not in strategy_columns
            or STRATEGY_USER_FK not in strategy_foreign_keys
        ):
            with op.batch_alter_table("strategies") as batch:
                if "user_id" not in strategy_columns:
                    batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
                if STRATEGY_USER_FK not in strategy_foreign_keys:
                    batch.create_foreign_key(
                        STRATEGY_USER_FK, "users", ["user_id"], ["id"]
                    )
        if STRATEGY_USER_INDEX not in _existing_indexes("strategies"):
            op.create_index(STRATEGY_USER_INDEX, "strategies", ["user_id"])

    if "user_settings" not in _existing_tables():
        op.create_table(
            "user_settings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("key", sa.String(), nullable=False),
            sa.Column("value", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=True),
            sa.UniqueConstraint("user_id", "key", name="uq_user_settings_user_key"),
        )
        op.create_index("ix_user_settings_id", "user_settings", ["id"])
        op.create_index("ix_user_settings_user_id", "user_settings", ["user_id"])


def downgrade() -> None:
    if "user_settings" in _existing_tables():
        op.drop_table("user_settings")

    if "strategies" in _existing_tables():
        strategy_columns = _existing_columns("strategies")
        strategy_foreign_keys = _existing_foreign_keys("strategies")
        strategy_indexes = _existing_indexes("strategies")
        if "user_id" in strategy_columns:
            with op.batch_alter_table("strategies") as batch:
                if STRATEGY_USER_FK in strategy_foreign_keys:
                    batch.drop_constraint(STRATEGY_USER_FK, type_="foreignkey")
                if STRATEGY_USER_INDEX in strategy_indexes:
                    batch.drop_index(STRATEGY_USER_INDEX)
                batch.drop_column("user_id")
