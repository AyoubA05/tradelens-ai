"""add performance_metrics

Revision ID: f6g7h8i9j0k1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-10
"""

from alembic import op
import sqlalchemy as sa

revision = "f6g7h8i9j0k1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "performance_metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.String(), nullable=True),
        sa.Column("period_end", sa.String(), nullable=True),
        sa.Column("trades_count", sa.Integer(), nullable=True),
        sa.Column("win_rate", sa.Float(), nullable=True),
        sa.Column("profit_factor", sa.Float(), nullable=True),
        sa.Column("avg_rr", sa.Float(), nullable=True),
        sa.Column("avg_win", sa.Float(), nullable=True),
        sa.Column("avg_loss", sa.Float(), nullable=True),
        sa.Column("total_pnl", sa.Float(), nullable=True),
        sa.Column("best_day", sa.String(), nullable=True),
        sa.Column("worst_day", sa.String(), nullable=True),
        sa.Column("best_strategy", sa.String(), nullable=True),
        sa.Column("worst_strategy", sa.String(), nullable=True),
        sa.Column("best_timeframe", sa.String(), nullable=True),
        sa.Column("worst_timeframe", sa.String(), nullable=True),
        sa.Column("computed_at", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_performance_metrics_user_id", "performance_metrics", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_performance_metrics_user_id", "performance_metrics")
    op.drop_table("performance_metrics")
