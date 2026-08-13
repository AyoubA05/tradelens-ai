"""Add auth_sessions.surface and require an explicit credential domain.

Website and Streamlit sessions were both plain sha256(token) rows in this table
with nothing to tell them apart, so any token validated on either surface. That
matters because their exposure differs by design: the website credential is an
HttpOnly cookie, while the Streamlit one rides in a URL and is a documented
leaky bearer. Interchangeability turned that asymmetry into a privilege bridge —
demonstrated on dev on 2026-08-13, where a Python-issued session was accepted by
the TypeScript website validator.

Two redundant controls fix it, and they fail differently:

  domain-separated hashing   sha256("tl.website.v1|"+t) vs sha256("tl.streamlit.v1|"+t)
                             prevents cross-surface acceptance by construction;
                             there is no filter to forget, because the hash
                             function each module uses IS the domain
  this column                makes the domain explicit, auditable and queryable,
                             and is checked as defence in depth

**No server default.** A default of 'website' would let a Streamlit creation
path that forgets the field silently produce a website-domain row. Every call
site has to choose, and an omission is a NOT NULL violation rather than a quiet
privilege grant.

**Safe only on an empty table.** Existing undomained rows cannot be classified
after the fact, and guessing would be worse than failing. Adding a NOT NULL
column with no default is itself the guard: it errors on a populated table. Both
dev and production were verified at 0 rows immediately before this ran.

No index on surface: token validation looks up by token_hash, which is already
unique and selective, and no operational query filters on surface alone.

Revision ID: w3x4y5z6a7b8
Revises: v2w3x4y5z6a7
Create Date: 2026-08-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "w3x4y5z6a7b8"
down_revision: Union[str, Sequence[str], None] = "v2w3x4y5z6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Fails loudly rather than guessing if anything is present.
    count = (
        op.get_bind().execute(sa.text("SELECT count(*) FROM auth_sessions")).scalar()
    )
    if count:
        raise RuntimeError(
            f"auth_sessions holds {count} undomained row(s). They cannot be "
            "classified as website or streamlit after the fact. Revoke or "
            "classify them explicitly, then re-run."
        )

    # batch_alter_table so this also works on SQLite, which cannot ALTER a
    # constraint in place and needs a table rebuild. On PostgreSQL it passes
    # straight through to plain ALTER statements.
    with op.batch_alter_table("auth_sessions") as batch:
        batch.add_column(sa.Column("surface", sa.String(16), nullable=False))
        batch.create_check_constraint(
            "ck_auth_sessions_surface", "surface IN ('website', 'streamlit')"
        )


def downgrade() -> None:
    with op.batch_alter_table("auth_sessions") as batch:
        batch.drop_constraint("ck_auth_sessions_surface", type_="check")
        batch.drop_column("surface")
