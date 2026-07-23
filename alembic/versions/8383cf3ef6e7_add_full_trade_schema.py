"""add full trade schema

Revision ID: 8383cf3ef6e7
Revises: 81413d7231da
Create Date: 2026-05-30 16:56:28.212257

The first revision was historically stamped after SQLAlchemy ``create_all``
had created the base tables. Recreate that historical base only when needed so
the migration chain can also initialize a blank database.
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8383cf3ef6e7"
down_revision: Union[str, Sequence[str], None] = "81413d7231da"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TRADE_COLUMNS = (
    ("trade_date", sa.String),
    ("day_of_week", sa.String),
    ("session", sa.String),
    ("asset_class", sa.String),
    ("bias", sa.String),
    ("stop_price", sa.Float),
    ("tp_price", sa.Float),
    ("position_size", sa.Float),
    ("risk_amount", sa.Float),
    ("reward_amount", sa.Float),
    ("rr_planned", sa.Float),
    ("strategy_used", sa.String),
    ("emotions_during", sa.String),
    ("emotions_after", sa.String),
    ("notes", sa.Text),
    ("ai_grade", sa.String),
    ("user_grade", sa.String),
    ("created_at", sa.String),
    ("updated_at", sa.String),
)


def _existing_tables() -> set:
    return set(inspect(op.get_bind()).get_table_names())


def _existing_columns(table_name: str) -> set:
    return {column["name"] for column in inspect(op.get_bind()).get_columns(table_name)}


def _create_historical_base_tables() -> None:
    tables = _existing_tables()

    if "strategies" not in tables:
        op.create_table(
            "strategies",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("trading_style", sa.String(), nullable=True),
            sa.Column("entry_rules", sa.Text(), nullable=True),
        )
        op.create_index("ix_strategies_id", "strategies", ["id"])

    if "trades" not in tables:
        op.create_table(
            "trades",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("asset", sa.String(), nullable=False),
            sa.Column("timeframe", sa.String(), nullable=True),
            sa.Column("direction", sa.String(), nullable=True),
            sa.Column("entry_price", sa.Float(), nullable=True),
            sa.Column("exit_price", sa.Float(), nullable=True),
            sa.Column("pnl", sa.Float(), nullable=True),
            sa.Column("result", sa.String(), nullable=True),
            sa.Column("rr_realized", sa.Float(), nullable=True),
            sa.Column("setup_type", sa.String(), nullable=True),
            sa.Column("emotions_before", sa.String(), nullable=True),
            sa.Column("strategy_id", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"]),
        )
        op.create_index("ix_trades_id", "trades", ["id"])

    if "screenshots" not in tables:
        op.create_table(
            "screenshots",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("file_path", sa.String(), nullable=False),
            sa.Column("trade_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["trade_id"], ["trades.id"]),
        )
        op.create_index("ix_screenshots_id", "screenshots", ["id"])


def upgrade() -> None:
    """Upgrade schema."""
    _create_historical_base_tables()

    existing_columns = _existing_columns("trades")
    for name, column_type in TRADE_COLUMNS:
        if name not in existing_columns:
            op.add_column("trades", sa.Column(name, column_type(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    if "trades" not in _existing_tables():
        return

    existing_columns = _existing_columns("trades")
    with op.batch_alter_table("trades") as batch:
        for name, _ in reversed(TRADE_COLUMNS):
            if name in existing_columns:
                batch.drop_column(name)
