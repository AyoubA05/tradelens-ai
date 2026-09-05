"""add ai analysis job guards

Revision ID: g3h4i5j6k7l8
Revises: f2g3h4i5j6k7
Create Date: 2026-09-02
"""

import sqlalchemy as sa
from alembic import op

revision = "g3h4i5j6k7l8"
down_revision = "f2g3h4i5j6k7"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("analysis_job_id", sa.Integer()),
    ("journal_job_id", sa.Integer()),
    ("grading_job_id", sa.Integer()),
    ("confirmed_at", sa.String()),
    ("confirmed_fields_json", sa.Text()),
)


def upgrade() -> None:
    for name, type_ in _COLUMNS:
        op.add_column("aianalysis", sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    for name, _type in reversed(_COLUMNS):
        op.drop_column("aianalysis", name)
