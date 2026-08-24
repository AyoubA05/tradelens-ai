"""Persist owner-scoped results for filtered-trade AI jobs.

Revision ID: c9d0e1f2g3h4
Revises: b8c9d0e1f2g3
"""

import sqlalchemy as sa
from alembic import op

revision = "c9d0e1f2g3h4"
down_revision = "b8c9d0e1f2g3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trade_summary_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("summary_key", sa.String(), nullable=False),
        sa.Column("filters_json", sa.Text(), nullable=False),
        sa.Column("content_md", sa.Text(), nullable=False),
        sa.Column("reviewed_trades", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "user_id", "summary_key", name="uq_trade_summary_results_user_key"
        ),
    )
    op.create_index(
        "ix_trade_summary_results_user_id", "trade_summary_results", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_trade_summary_results_user_id", table_name="trade_summary_results"
    )
    op.drop_table("trade_summary_results")
