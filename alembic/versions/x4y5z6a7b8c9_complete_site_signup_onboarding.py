"""Complete personal onboarding already collected by site signup.

The site signup endpoint has always required and persisted full name, birthday,
and referral source. It nevertheless created the account with
``onboarding_completed = false``, which sent the user through the same fields a
second time after email verification.

Only opaque site-created accounts with every required stored field are
promoted. Legacy usernames such as ``ayoub`` and ``Ayoub`` cannot match the
opaque username shape and are therefore untouched. The Strategy Profile flag
is deliberately not updated; Streamlit still owns and enforces that gate.

Revision ID: x4y5z6a7b8c9
Revises: w3x4y5z6a7b8
Create Date: 2026-08-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "x4y5z6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "w3x4y5z6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            UPDATE users
               SET onboarding_completed = true
             WHERE onboarding_completed = false
               AND username LIKE 'u!_%' ESCAPE '!'
               AND length(username) = 18
               AND email IS NOT NULL
               AND full_name IS NOT NULL
               AND trim(full_name) <> ''
               AND birthday IS NOT NULL
               AND referral_source IN
                   ('TikTok', 'Instagram', 'YouTube', 'Google/Search',
                    'Friend', 'Reddit', 'X/Twitter', 'Other')
            """
        )
    )


def downgrade() -> None:
    # This is an irreversible state normalization, not a schema change. Once an
    # account's already-stored personal details have been recognized as
    # complete, setting the flag back to false would knowingly recreate the
    # duplicate form and could also regress accounts completed by the old flow.
    # A no-op is the only downgrade that preserves truthful user state.
    pass
