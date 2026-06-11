"""catch up schema drift - add missing Trade and Screenshot columns

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-09 12:00:00.000000

Columns that exist in models.py but were never added in any prior migration's
upgrade() function. Uses column-existence checks so the migration is idempotent
regardless of whether the DB was created via init_db or alembic upgrade head.

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_columns(table_name: str) -> set:
    bind = op.get_bind()
    return {c["name"] for c in inspect(bind).get_columns(table_name)}


def upgrade() -> None:
    trade_cols = _existing_columns("trades")
    missing_trade = {
        "emotions_before": sa.Column("emotions_before", sa.String(), nullable=True),
        "rr_realized": sa.Column("rr_realized", sa.Float(), nullable=True),
        "exit_price": sa.Column("exit_price", sa.Float(), nullable=True),
        "setup_type": sa.Column("setup_type", sa.String(), nullable=True),
        "timeframe": sa.Column("timeframe", sa.String(), nullable=True),
    }
    for col_name, col_def in missing_trade.items():
        if col_name not in trade_cols:
            op.add_column("trades", col_def)

    screenshot_cols = _existing_columns("screenshots")
    missing_screenshot = {
        "width": sa.Column("width", sa.Integer(), nullable=True),
        "height": sa.Column("height", sa.Integer(), nullable=True),
        "uploaded_at": sa.Column("uploaded_at", sa.String(), nullable=True),
    }
    for col_name, col_def in missing_screenshot.items():
        if col_name not in screenshot_cols:
            op.add_column("screenshots", col_def)


def downgrade() -> None:
    # SQLite does not support DROP COLUMN natively before 3.35.
    # These are nullable additive columns — downgrade is a no-op.
    pass
