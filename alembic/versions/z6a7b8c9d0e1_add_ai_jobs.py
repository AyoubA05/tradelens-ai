"""Add ai_jobs for asynchronous AI work.

Revision ID: z6a7b8c9d0e1
Revises: y5z6a7b8c9d0
"""

import sqlalchemy as sa
from alembic import op

revision = "z6a7b8c9d0e1"
down_revision = "y5z6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column(
            "status", sa.String(), nullable=False, server_default=sa.text("'queued'")
        ),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column("result_ref", sa.String(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column(
            "attempts", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_ai_jobs_user_key"),
    )
    op.create_index("ix_ai_jobs_user_id", "ai_jobs", ["user_id"])
    # The worker's claim query filters on status and orders by id.
    op.create_index("ix_ai_jobs_status", "ai_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_ai_jobs_status", table_name="ai_jobs")
    op.drop_index("ix_ai_jobs_user_id", table_name="ai_jobs")
    op.drop_table("ai_jobs")
