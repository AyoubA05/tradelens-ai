"""Add trade_drafts: one in-progress New Trade form per owner.

A draft is its own table, never a flag on trades, so an incomplete draft is
structurally incapable of being picked up by any query, filter, metric or
export over the trades table (Decision 3).

Revision ID: e1f2g3h4i5j6
Revises: d0e1f2g3h4i5
"""

import sqlalchemy as sa
from alembic import op

revision = "e1f2g3h4i5j6"
down_revision = "d0e1f2g3h4i5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trade_drafts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_trade_drafts_user"),
    )
    # The unique constraint above already gives most databases an index on
    # user_id; this index is explicit and named so "indexed" holds even on a
    # backend that does not derive one from the constraint automatically.
    op.create_index(
        "ix_trade_drafts_user_id", "trade_drafts", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_trade_drafts_user_id", table_name="trade_drafts")
    op.drop_table("trade_drafts")
