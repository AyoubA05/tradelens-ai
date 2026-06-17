"""add SMC/ICT fields to trades (Phase 1)

Revision ID: g7h8i9j0k1l2
Revises: f6g7h8i9j0k1
Create Date: 2026-06-17

Adds 11 SMC/ICT columns to the trades table.
Idempotent: skips any column that already exists.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "g7h8i9j0k1l2"
down_revision: Union[str, Sequence[str], None] = "f6g7h8i9j0k1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_columns(table_name: str) -> set:
    bind = op.get_bind()
    return {c["name"] for c in inspect(bind).get_columns(table_name)}


def upgrade() -> None:
    existing = _existing_columns("trades")
    new_cols = {
        "htf_bias":          sa.Column("htf_bias",          sa.String(),  nullable=True),
        "killzone":          sa.Column("killzone",          sa.String(),  nullable=True),
        "liquidity_sweep":   sa.Column("liquidity_sweep",   sa.Integer(), nullable=True),
        "fvg_used":          sa.Column("fvg_used",          sa.Integer(), nullable=True),
        "order_block_used":  sa.Column("order_block_used",  sa.Integer(), nullable=True),
        "bos":               sa.Column("bos",               sa.Integer(), nullable=True),
        "choch":             sa.Column("choch",             sa.Integer(), nullable=True),
        "confirmation_model": sa.Column("confirmation_model", sa.String(), nullable=True),
        "entry_type":        sa.Column("entry_type",        sa.String(),  nullable=True),
        "mistake_tags":      sa.Column("mistake_tags",      sa.Text(),    nullable=True),
        "followed_rules":    sa.Column("followed_rules",    sa.Integer(), nullable=True),
    }
    for col_name, col_def in new_cols.items():
        if col_name not in existing:
            op.add_column("trades", col_def)


def downgrade() -> None:
    # SQLite <3.35 does not support DROP COLUMN; use recreate pattern.
    # For dev/SQLite we implement a best-effort pass; Postgres prod would need column drops.
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return

    smc_cols = [
        "htf_bias", "killzone", "liquidity_sweep", "fvg_used", "order_block_used",
        "bos", "choch", "confirmation_model", "entry_type", "mistake_tags", "followed_rules",
    ]
    for col in smc_cols:
        op.drop_column("trades", col)
