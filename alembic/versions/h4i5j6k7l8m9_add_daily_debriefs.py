"""add daily_debriefs; review provenance on weekly_reviews

Revision ID: h4i5j6k7l8m9
Revises: g3h4i5j6k7l8
Create Date: 2026-09-14

Phase 10A (decisions R1, C1). `daily_debriefs` stores one owner's debrief per
day with its provenance. `weekly_reviews` gains nullable provenance columns so
legacy and Streamlit-saved rows stay valid.
"""

import sqlalchemy as sa
from alembic import op

revision = "h4i5j6k7l8m9"
down_revision = "g3h4i5j6k7l8"
branch_labels = None
depends_on = None

_WEEKLY_COLUMNS = (
    ("input_fingerprint", sa.String(64)),
    ("job_id", sa.Integer()),
    ("updated_at", sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    op.create_table(
        "daily_debriefs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("day", sa.String(10), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("content_md", sa.Text(), nullable=False),
        sa.Column("stats_json", sa.Text(), nullable=False),
        sa.Column("reviewed_trades", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "day", name="uq_daily_debriefs_user_day"),
    )
    op.create_index("ix_daily_debriefs_user_id", "daily_debriefs", ["user_id"])
    with op.batch_alter_table("weekly_reviews") as batch:
        for name, type_ in _WEEKLY_COLUMNS:
            batch.add_column(sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("weekly_reviews") as batch:
        for name, _type in reversed(_WEEKLY_COLUMNS):
            batch.drop_column(name)
    op.drop_index("ix_daily_debriefs_user_id", table_name="daily_debriefs")
    op.drop_table("daily_debriefs")
