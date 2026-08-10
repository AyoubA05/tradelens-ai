# Site-Hosted Authentication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move sign-in, sign-up, and password reset from the Streamlit app to a Next.js app on `tradelensai.io`, handing off into Streamlit through a one-time credential and a revocable server-side session, with email verification and a first-run Strategy Profile step for new users.

**Architecture:** One Vercel project rooted at `web/` serves the existing static marketing site from `public/` plus new React auth routes and Node serverless auth endpoints. Both runtimes share one Neon Postgres database and one `TRADELENS_SESSION_SECRET`. Authentication succeeds on the site, mints a 120-second single-use handoff token, and redirects to Streamlit, which atomically redeems it and opens a revocable `auth_sessions` record.

**Tech Stack:** Next.js + TypeScript + Tailwind + shadcn structure + framer-motion (site); Python 3.11 + Streamlit 1.50 + SQLAlchemy 2.x + Alembic (app); Neon Postgres; bcrypt; nodemailer / stdlib SMTP; pytest + vitest.

**Spec:** `docs/superpowers/specs/2026-08-10-site-hosted-auth-design.md`

## Global Constraints

- **Model:** `claude-opus-5` only, via `services/ai_client.py`. This project adds no AI calls.
- **No Streamlit imports inside `services/` or `db/`.**
- `prompts/` files are LOCKED — extend contracts only.
- Every Alembic revision implements `downgrade()`.
- `DEMO_MODE=true` returns cached output — zero API spend in tests.
- Secrets come from the settings layer only. Never hardcoded, never logged, never in an API response, never in a client bundle.
- **Baseline: 2178 passed, 7 skipped, 0 ruff violations** (measured 2026-08-10). CLAUDE.md's "136 tests" is stale by an order of magnitude — it dates from Week 5 Day 0. No phase may regress the real number.
- **Python 3.9 in `.venv`**, despite CLAUDE.md saying 3.11. New modules need `from __future__ import annotations` for `X | None` syntax. Run tools as `.venv/bin/python -m <tool>`; the console scripts are not on PATH.
- Gates: `pytest tests/ -v --tb=short`, `ruff check src/ scripts/`, `black --check src/ scripts/`.
- Product identity: post-trade reflection journal. No signals, predictions, or trade advice — including UI copy on the new auth pages.
- `APP_ORIGIN` / `SITE_ORIGIN` are the only sources for those hostnames. Never hardcode `tradelenai.streamlit.app`.
- The old Streamlit login stays working until Phase 9.

---

# PHASE 1 — Neon inspection, backup, migration, backfill

**Nothing in this phase runs against production until the Phase 1 Gate below is
signed off by the owner.**

## Phase 1 Gate — owner review pack

Produce this, show it, and stop. Do not proceed unhandled.

### Affected tables

| Table | Change | Row count impact |
|---|---|---|
| `users` | `ALTER TABLE` adds 8 nullable-or-defaulted columns | **zero** |
| `auth_handoffs` | new table | new, empty |
| `auth_sessions` | new table | new, empty |
| `auth_attempts` | new table | new, empty |
| all others | untouched | zero |

No table is dropped, renamed, recreated, or imported over.

### Backup / branching strategy

The primary branch is **`production`**, not `main`. All branches are cut from it.

```
production  (br-soft-morning-auxx44gz)   ← never modified during Phase 1A
├── pre-auth-migration-2026-08-10        ← snapshot / rollback target
├── dev-auth-migration                   ← rehearsal; uses its copied neondb
├── alembic-reference                    ← uses a NEW EMPTY db: alembic_reference
└── backup-restore-check                 ← uses a NEW EMPTY db: restore_check
```

**A Neon branch is a copy of its parent, so no branch is ever "empty".** The
emptiness has to come from a *separate database created inside* the branch. Two
branches need that:

| Branch | Copied `neondb` | Separate empty database | Purpose |
|---|---|---|---|
| `alembic-reference` | left untouched | `alembic_reference` | canonical schema for revision `r8s9t0u1v2w3` |
| `backup-restore-check` | left untouched | `restore_check` | proves the `pg_dump` is restorable |

`alembic-reference/alembic_reference` is what makes Phase 1A possible: an empty
database migrated to `r8s9t0u1v2w3` from nothing, on the same PostgreSQL 17
engine, so its schema is by construction exactly what that revision *means*.
Comparing `dev-auth-migration/neondb` against it answers "is production
equivalent to `r8s9t0u1v2w3`?" with evidence instead of assertion. It must be
Postgres — diffing against SQLite would bury real differences under type noise.

**Alembic-from-zero is never run against a copied `neondb`.** Doing so would
attempt every revision from the beginning against a database that already has
the tables.

`backup-restore-check/restore_check` restores the logical dump into an empty
target and verifies schema and row counts. Restoring over a populated
production clone would prove nothing and destroy the clone.

1. Neon Console → project `tradelens-prod` → **Branches** → create branch `pre-auth-migration-2026-08-10` from `production` at current LSN. This is a copy-on-write snapshot; restoring is a branch promote, not a data import.
2. Also take a logical dump as an independent artifact, in case the branch is lost:
   `pg_dump "$DATABASE_URL" --format=custom --no-owner --file=backup-2026-08-10.dump`
3. **Verify the backup restores** into a scratch branch before relying on it. An unverified backup is not a backup.
4. Create a second branch `dev-auth-migration` — the migration runs here first.

### Rollback strategy

| Stage | Rollback |
|---|---|
| Reconciliation or migration on `dev-auth-migration` fails | Delete the branch and re-cut it from `production`. Production untouched. |
| Migration on production fails mid-run | Alembic runs each revision in a transaction; a failure rolls back automatically. Verify with `alembic current`. |
| Migration succeeded but is wrong | `alembic downgrade -1` — tested on the dev branch first, in Task 1.5. |
| Catastrophic | Promote `pre-auth-migration-2026-08-10` back to primary. |

The old data is never deleted or overwritten at any stage.

### Required new secrets — Streamlit Cloud

| Variable | What it is |
|---|---|
| `TRADELENS_SESSION_SECRET` | 32+ bytes of cryptographic randomness (`openssl rand -base64 48`). Signs sessions and verification codes. **Byte-identical to Vercel's.** |
| `TRADELENS_SMTP_HOST` | Mail server hostname |
| `TRADELENS_SMTP_PORT` | `587` (STARTTLS) or `465` (implicit TLS) |
| `TRADELENS_SMTP_USER` | SMTP username / API-key identifier |
| `TRADELENS_SMTP_PASSWORD` | SMTP password / API key |
| `TRADELENS_SMTP_FROM` | Sender, e.g. `TradeLens <no-reply@tradelensai.io>`. Must be authorised for the domain by the provider or mail is silently dropped. |

### Required Vercel environment variables

The same six, plus: `DATABASE_URL` (same Neon string, **pooled** endpoint — serverless opens many short connections), `TRADELENS_INVITE_CODE`, `SIGNUP_MODE=invite`, `APP_ORIGIN`, `SITE_ORIGIN`.

The Anthropic key is **not** added to Vercel — no AI call exists in the auth path.

### Migration being applied

The full `upgrade()` / `downgrade()` source is in Task 1.3 below. Read it before signing off.

---

**Files:**
- Create: `alembic/versions/s9t0u1v2w3x4_add_site_auth_and_onboarding.py`
- Create: `scripts/db_inventory.py`
- Modify: `src/tradelens/db/models.py:7-23` (User), append 3 model classes
- Test: `tests/test_migration_site_auth.py`

**Interfaces:**
- Consumes: existing `Base`, `User`, `Strategy` from `src/tradelens/db/models.py`
- Produces: `User.full_name`, `User.birthday`, `User.referral_source`, `User.referral_source_other`, `User.onboarding_completed`, `User.strategy_profile_completed`, `User.email_verified_at`, `User.email_verification_required`; models `AuthHandoff`, `AuthSession`, `AuthAttempt`

### Task 1.1: Inventory the production database

- [ ] **Step 1: Write the inventory script**

```python
# scripts/db_inventory.py
"""Read-only census of the production database. Prints counts, never data.

Run before and after a migration; the two outputs must match for every table
this migration is not supposed to change.
"""

from sqlalchemy import inspect, text

from src.tradelens.db.session import SessionLocal, engine

TABLES = [
    "users", "trades", "strategies", "corrections", "weekly_reviews",
    "screenshots", "ai_analyses", "performance_metrics", "ai_usage_log",
]


def main() -> None:
    insp = inspect(engine)
    present = set(insp.get_table_names())
    db = SessionLocal()
    try:
        print(f"alembic revision: {db.execute(text('SELECT version_num FROM alembic_version')).scalar()}")
        for name in TABLES:
            if name not in present:
                print(f"{name:24} MISSING")
                continue
            count = db.execute(text(f"SELECT count(*) FROM {name}")).scalar()
            print(f"{name:24} {count}")
        # Decides whether the bootstrap credential path is already unreachable.
        users = db.execute(text("SELECT count(*) FROM users")).scalar()
        print(f"\nbootstrap login reachable: {users == 0}")
        print("users with email:       ",
              db.execute(text("SELECT count(*) FROM users WHERE email IS NOT NULL")).scalar())
        print("users with active strategy:",
              db.execute(text("SELECT count(DISTINCT user_id) FROM strategies WHERE is_active = 1")).scalar())
    finally:
        db.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it against the production `DATABASE_URL`, read-only**

Run: `DATABASE_URL="<neon url>" python -m scripts.db_inventory | tee docs/audit/db-inventory-before.txt`
Expected: a revision of `r8s9t0u1v2w3` and a row count for every table.

- [ ] **Step 3: Confirm the Alembic revision matches the repo head**

Run: `alembic heads`
Expected: `r8s9t0u1v2w3`. **If production reports anything else, stop** — the repo and production have diverged and that must be resolved before migrating.

- [ ] **Step 4: Record the bootstrap finding**

If `users` > 0, the `TRADELENS_USERNAME`/`PASSWORD` path is already unreachable in production (spec §3). Note it in `docs/audit/db-inventory-before.txt`. Change nothing.

- [ ] **Step 5: Commit the script and the inventory**

```bash
git add scripts/db_inventory.py docs/audit/db-inventory-before.txt
git commit -m "chore(db): inventory production before auth migration"
```

### Task 1.2: Add the ORM models

- [ ] **Step 1: Write the failing test**

```python
# tests/test_migration_site_auth.py
from datetime import date, datetime, timezone

from src.tradelens.db.models import AuthAttempt, AuthHandoff, AuthSession, User


def test_user_carries_the_onboarding_and_profile_columns():
    user = User(username="ayoub", password_hash="x")
    # Defaults are server-side, so a bare instance has them unset, not wrong.
    for column in (
        "full_name", "birthday", "referral_source", "referral_source_other",
        "onboarding_completed", "strategy_profile_completed",
        "email_verified_at", "email_verification_required",
    ):
        assert hasattr(user, column), f"User is missing {column}"


def test_birthday_is_a_real_date_and_verification_is_a_timestamp():
    columns = User.__table__.columns
    assert columns["birthday"].type.python_type is date
    assert columns["email_verified_at"].type.python_type is datetime
    assert columns["email_verified_at"].type.timezone is True
    assert columns["onboarding_completed"].type.python_type is bool


def test_auth_tables_hash_their_credentials():
    # The raw token must never be storable — only its hash.
    for model in (AuthHandoff, AuthSession):
        assert "token_hash" in model.__table__.columns
        assert "token" not in model.__table__.columns
        assert model.__table__.columns["token_hash"].unique is True
    assert "bucket" in AuthAttempt.__table__.columns
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_migration_site_auth.py -v`
Expected: FAIL — `ImportError: cannot import name 'AuthHandoff'`

- [ ] **Step 3: Extend the `User` model**

In `src/tradelens/db/models.py`, add to `class User` after `is_active`:

```python
    # Collected at signup by the site-hosted flow. Nullable because accounts
    # created before that flow existed never supplied them; the signup endpoint
    # requires them for new accounts.
    full_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    birthday: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    referral_source: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    referral_source_other: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    onboarding_completed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_false()
    )
    strategy_profile_completed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_false()
    )

    # NULL means unverified; a timestamp means verified. Deliberately NOT
    # backfilled for legacy rows — their address genuinely was never verified,
    # and recording otherwise would make the column a lie. The legacy rule below
    # is what keeps them signing in.
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # False for every account that predates verification. The login gate reads
    # this, so legacy users pass without us pretending they verified.
    email_verification_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_true()
    )
```

Add the imports in the same edit (the repo's formatter hook strips unused imports):

```python
from datetime import date, datetime
from sqlalchemy import Boolean, Date, DateTime, false as sa_false, true as sa_true
```

- [ ] **Step 4: Add the three auth tables**

Append to `src/tradelens/db/models.py`:

```python
class AuthHandoff(Base):
    """One-time credential handing a signed-in user from the site to Streamlit.

    Only the SHA-256 hash is stored, so a database read yields nothing usable.
    Redemption is a conditional UPDATE, never a read-then-write: Streamlit reruns
    scripts concurrently and two tabs can race for the same row.
    """

    __tablename__ = "auth_handoffs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AuthSession(Base):
    """Revocable server-side session. Replaces the self-contained HMAC token.

    The old token could not be revoked, so signing out left a working credential
    behind for up to 24 hours. Revocation here is a row update, which is what
    actually makes sign-out mean something.
    """

    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AuthAttempt(Base):
    """One row per authentication attempt, for DB-backed rate limiting.

    Serverless instances share no memory, so an in-process counter is not a
    limit at all. `bucket` is an opaque key such as "ip:1.2.3.4" or
    "id:someone@example.com"; `succeeded` exists so per-identifier limits can
    count failures only and a success can clear the counter.
    """

    __tablename__ = "auth_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bucket: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_false())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
```

- [ ] **Step 5: Run the test**

Run: `pytest tests/test_migration_site_auth.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/tradelens/db/models.py tests/test_migration_site_auth.py
git commit -m "feat(db): add onboarding columns and auth tables to the models"
```

### Task 1.3: Write the migration

- [ ] **Step 1: Write the failing round-trip test**

```python
# append to tests/test_migration_site_auth.py
import subprocess


def _alembic(*args: str, url: str) -> subprocess.CompletedProcess:
    import os
    env = {**os.environ, "DATABASE_URL": url}
    return subprocess.run(
        ["alembic", *args], capture_output=True, text=True, env=env, check=False
    )


def test_migration_upgrades_and_downgrades_cleanly(tmp_path):
    url = f"sqlite:///{tmp_path / 'roundtrip.db'}"
    up = _alembic("upgrade", "head", url=url)
    assert up.returncode == 0, up.stderr
    down = _alembic("downgrade", "-1", url=url)
    assert down.returncode == 0, down.stderr
    again = _alembic("upgrade", "head", url=url)
    assert again.returncode == 0, again.stderr
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_migration_site_auth.py::test_migration_upgrades_and_downgrades_cleanly -v`
Expected: FAIL — head is still `r8s9t0u1v2w3`, so `downgrade -1` removes the email column instead of this revision.

- [ ] **Step 3: Write the migration**

```python
# alembic/versions/s9t0u1v2w3x4_add_site_auth_and_onboarding.py
"""Add onboarding/profile columns and the site-auth tables.

Additive only. Every users column is nullable or carries a server default, so
the ALTER cannot fail on existing rows and no row count changes anywhere.

The backfill encodes one deliberate asymmetry, and it is the point of the whole
revision: legacy accounts get `email_verification_required = False` rather than
a fabricated `email_verified_at`. Their address really was never verified, and
writing a timestamp saying otherwise would put a falsehood in the data to save
one boolean. The login gate reads the flag, so they sign in unaffected.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "s9t0u1v2w3x4"
down_revision: Union[str, Sequence[str], None] = "r8s9t0u1v2w3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_USER_COLUMNS = (
    "full_name", "birthday", "referral_source", "referral_source_other",
    "onboarding_completed", "strategy_profile_completed",
    "email_verified_at", "email_verification_required",
)


def upgrade() -> None:
    op.add_column("users", sa.Column("full_name", sa.String(), nullable=True))
    op.add_column("users", sa.Column("birthday", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("referral_source", sa.String(), nullable=True))
    op.add_column("users", sa.Column("referral_source_other", sa.String(), nullable=True))
    op.add_column(
        "users",
        sa.Column("onboarding_completed", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
    )
    op.add_column(
        "users",
        sa.Column("strategy_profile_completed", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
    )
    op.add_column(
        "users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column("email_verification_required", sa.Boolean(), nullable=False,
                  server_default=sa.true()),
    )

    # --- backfill: every row that exists right now is, by definition, legacy ---

    # They never saw the personal-info form; do not trap them behind it.
    op.execute("UPDATE users SET onboarding_completed = true")

    # The explicit legacy compatibility rule. email_verified_at stays NULL.
    op.execute("UPDATE users SET email_verification_required = false")

    # Users who already have an active profile skip the first-run step; users
    # who do not get it exactly once. Correlated subquery rather than a JOIN so
    # the statement is identical on SQLite and Postgres.
    op.execute(
        """
        UPDATE users SET strategy_profile_completed = true
        WHERE EXISTS (
            SELECT 1 FROM strategies
            WHERE strategies.user_id = users.id AND strategies.is_active = 1
        )
        """
    )

    op.create_table(
        "auth_handoffs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_auth_handoffs_token_hash", "auth_handoffs", ["token_hash"], unique=True)
    op.create_index("ix_auth_handoffs_user_id", "auth_handoffs", ["user_id"])

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_auth_sessions_token_hash", "auth_sessions", ["token_hash"], unique=True)
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])

    op.create_table(
        "auth_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bucket", sa.String(200), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("succeeded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_auth_attempts_bucket", "auth_attempts", ["bucket"])
    op.create_index("ix_auth_attempts_created_at", "auth_attempts", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_auth_attempts_created_at", table_name="auth_attempts")
    op.drop_index("ix_auth_attempts_bucket", table_name="auth_attempts")
    op.drop_table("auth_attempts")

    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_token_hash", table_name="auth_sessions")
    op.drop_table("auth_sessions")

    op.drop_index("ix_auth_handoffs_user_id", table_name="auth_handoffs")
    op.drop_index("ix_auth_handoffs_token_hash", table_name="auth_handoffs")
    op.drop_table("auth_handoffs")

    # batch_alter_table so the drop also works on SQLite, which cannot DROP
    # COLUMN in older versions and needs a table rebuild.
    with op.batch_alter_table("users") as batch:
        for column in reversed(_USER_COLUMNS):
            batch.drop_column(column)
```

- [ ] **Step 4: Run the round-trip test**

Run: `pytest tests/test_migration_site_auth.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/s9t0u1v2w3x4_add_site_auth_and_onboarding.py tests/test_migration_site_auth.py
git commit -m "feat(db): migration for site auth tables and onboarding columns"
```

### Task 1.4: Prove the backfill rules

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_migration_site_auth.py
from sqlalchemy import create_engine, text


def _seed_pre_migration(url: str) -> None:
    """Build a schema at the previous revision and put legacy rows in it."""
    _alembic("upgrade", "r8s9t0u1v2w3", url=url)
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO users (id, username, password_hash, email, is_active) "
            "VALUES (1, 'withprofile', 'h', 'a@example.com', 1), "
            "       (2, 'noprofile',   'h', NULL,            1)"
        ))
        conn.execute(text(
            "INSERT INTO strategies (user_id, name, is_active) VALUES (1, 'SMC', 1)"
        ))


def test_backfill_preserves_legacy_users_without_faking_verification(tmp_path):
    url = f"sqlite:///{tmp_path / 'backfill.db'}"
    _seed_pre_migration(url)
    assert _alembic("upgrade", "head", url=url).returncode == 0

    engine = create_engine(url)
    with engine.begin() as conn:
        rows = dict(conn.execute(text(
            "SELECT username, onboarding_completed FROM users"
        )).all())
        assert rows == {"withprofile": 1, "noprofile": 1}, "legacy users must skip onboarding"

        # The heart of the legacy rule: exempt, not fraudulently verified.
        verified, required = conn.execute(text(
            "SELECT email_verified_at, email_verification_required "
            "FROM users WHERE username = 'withprofile'"
        )).one()
        assert verified is None, "must not fabricate a verification timestamp"
        assert required == 0, "legacy users must be exempt from verification"

        profile = dict(conn.execute(text(
            "SELECT username, strategy_profile_completed FROM users"
        )).all())
        assert profile["withprofile"] == 1, "existing profile means already completed"
        assert profile["noprofile"] == 0, "no profile means one first-run pass"


def test_migration_changes_no_row_counts(tmp_path):
    url = f"sqlite:///{tmp_path / 'counts.db'}"
    _seed_pre_migration(url)
    engine = create_engine(url)
    with engine.begin() as conn:
        before = {t: conn.execute(text(f"SELECT count(*) FROM {t}")).scalar()
                  for t in ("users", "strategies")}
    assert _alembic("upgrade", "head", url=url).returncode == 0
    with engine.begin() as conn:
        after = {t: conn.execute(text(f"SELECT count(*) FROM {t}")).scalar()
                 for t in ("users", "strategies")}
    assert before == after
```

- [ ] **Step 2: Run them**

Run: `pytest tests/test_migration_site_auth.py -v`
Expected: PASS — the migration from Task 1.3 already implements this. If any fail, the backfill SQL is wrong; fix it, not the test.

- [ ] **Step 3: Commit**

```bash
git add tests/test_migration_site_auth.py
git commit -m "test(db): lock the legacy backfill rules"
```

### Task 1A: Schema reconciliation — BLOCKS the migration

Production has the application schema but no Alembic tracking (F1) and is
missing at least one index the target revision creates (F2). Nothing may be
stamped or migrated until the gap is measured and closed.

**Runs on `dev-auth-migration` and `alembic-reference` only. Production is not
touched at any point in this task.**

**Credential hygiene, applying to every step.** Branch-specific `DATABASE_URL`
values live in the local environment only. They are never committed, printed,
logged, written into a `docs/audit/` file, or left in shell output that gets
committed. Evidence files carry schema and count information only. Commands
below are written as `DATABASE_URL="<...>"` and must be invoked with the value
supplied from the environment, not typed inline into anything recorded.

- [ ] **1A.1 — Build the canonical reference.** Against the **empty
      `alembic_reference` database inside the `alembic-reference` branch** —
      never the copied `neondb`:
      `DATABASE_URL="<alembic-reference/alembic_reference>" .venv/bin/python -m alembic upgrade r8s9t0u1v2w3`
      Confirm `alembic current` reports `r8s9t0u1v2w3`.

- [ ] **1A.2 — Verify the logical backup.** Restore the `pg_dump` into the empty
      `restore_check` database inside `backup-restore-check`, then run
      `scripts.db_inventory` against it and confirm the row counts match the
      production census. This is the only evidence that the dump is usable.

- [ ] **1A.3 — Produce the drift report.**
      `REFERENCE_URL="<alembic-reference/alembic_reference>" TARGET_URL="<dev-auth-migration/neondb>" .venv/bin/python -m scripts.schema_drift | tee docs/audit/schema-drift-2026-08-10.txt`
      Covers tables, columns, types, nullability, defaults, primary keys,
      foreign keys, unique constraints, and indexes across **every** application
      table — not just `users`. Output is split into **A. benign/environment**
      and **B. genuine drift**; exit code is 1 while any category B item remains.

- [ ] **1A.4 — Stop and report.** Bring the full report to the owner before any
      reconciliation or stamp. Category B items are decided by the owner, not
      silently repaired.

- [ ] **1A.5 — Reconcile category B on the dev branch**, once approved.

      **Reconcile to what the reference database actually contains, not to an
      assumption from `models.py`.** For the email uniqueness gap, the reference
      decides every detail: whether the object is a unique index or a `UNIQUE`
      constraint, its exact name, and any index PostgreSQL generates alongside
      a constraint. Naming a specific `CREATE UNIQUE INDEX ix_users_email`
      statement in advance would be guessing at the answer the comparison exists
      to produce — and a mismatch in kind or name leaves the schema *still*
      unequal to the revision while looking repaired.

      **Before adding any uniqueness enforcement, check for duplicate non-NULL
      values.** It fails on a populated table otherwise. Production has
      `users_with_email = 0`, so this is safe today, but the check belongs in
      the procedure because it will not always be.

- [ ] **1A.6 — Re-run the drift report.** It must exit 0. A clean report is the
      *only* thing that makes the next step legitimate.

- [ ] **1A.7 — Stamp the dev branch.**
      `DATABASE_URL="<dev-auth-migration/neondb>" .venv/bin/python -m alembic stamp r8s9t0u1v2w3`
      then confirm `alembic current` reports `r8s9t0u1v2w3`.

      `stamp` asserts "this schema already is that revision". Running it to
      silence a missing-revision error, rather than because a diff proved the
      claim, converts a visible problem into an invisible one that surfaces
      later somewhere unrelated. 1A.6 is what earns this command.

- [ ] **1A.8 — Rehearse the migration** (this is Task 1.5, run here on the dev
      branch): `alembic upgrade s9t0u1v2w3x4` → verify row counts unchanged →
      verify the backfill → `downgrade -1` → verify → `upgrade head` → verify
      again → re-run the drift report.

      Expected backfill on the two production accounts: both
      `onboarding_completed = true`, both `email_verification_required = false`,
      both `email_verified_at` NULL, exactly one
      `strategy_profile_completed = true`, exactly one `false`.

- [ ] **1A.9 — STOP.** Report to the owner. No production reconciliation, no
      production stamp, no `s9t0u1v2w3x4` against production without explicit
      approval of the full drift and reconciliation report.

**Exit:** the drift report exits 0 on `dev-auth-migration`, that branch is
stamped and migrated and rehearsed both directions, the backup is proven
restorable, and the owner has approved reconciliation for production.

### Task 1A.10: Alembic becomes the schema authority (DONE — commit `e3fdb43`+)

Not merely a guard. The division of responsibility is now enforced in code and
tested:

| Database | Who owns the schema | What `init_db` does |
|---|---|---|
| Deployed (tracked by Alembic) | Alembic migrations | raises `SchemaManagedByAlembicError` |
| Remote, untracked | nobody yet — must be migrated | raises `UnmanagedRemoteSchemaError` unless `allow_unmanaged_remote=True` is passed explicitly |
| Local SQLite | `init_db` | creates and reconciles, as before |

`ui/app.py` no longer calls `init_db()`. It calls `bootstrap_if_local()`, which
acts only on an untracked local SQLite file and is a documented no-op against
anything else — so **application startup can no longer mutate a deployed schema
behind Alembic's back**, which is the specific behaviour that produced this
whole situation.

Covered by `tests/test_init_db_alembic_authority.py`, including a source-level
assertion that `app.py` never calls `init_db()` again — the risky call is one
word away from the safe one, and nothing else in the suite would notice.

### Task 1.5: Rehearse the migration on the dev branch

- [ ] **Step 1: Confirm the owner has created the branches** from the Phase 1 Gate. Do not create or delete Neon branches unattended.

- [ ] **Step 2: Migrate the dev branch**

Run: `DATABASE_URL="<dev-auth-migration url>" alembic upgrade head`
Expected: exit 0, no error.

- [ ] **Step 3: Inventory the dev branch and diff**

Run: `DATABASE_URL="<dev branch url>" python -m scripts.db_inventory > /tmp/after.txt && diff docs/audit/db-inventory-before.txt /tmp/after.txt`
Expected: only the `alembic revision` line differs. **Any row-count difference is a stop condition.**

- [ ] **Step 4: Verify the backfill on real data**

```sql
SELECT
  count(*) FILTER (WHERE onboarding_completed)            AS onboarded,
  count(*) FILTER (WHERE NOT email_verification_required) AS legacy_exempt,
  count(*) FILTER (WHERE email_verified_at IS NOT NULL)   AS verified,
  count(*) FILTER (WHERE strategy_profile_completed)      AS has_profile,
  count(*)                                                AS total
FROM users;
```

Expected: `onboarded = legacy_exempt = total`; `verified = 0`; `has_profile` equals the distinct active-strategy user count from Task 1.1.

- [ ] **Step 5: Test the downgrade on the dev branch**

Run: `DATABASE_URL="<dev branch url>" alembic downgrade -1 && DATABASE_URL="<dev branch url>" alembic upgrade head`
Expected: both succeed. A downgrade that has never been executed is not a rollback plan.

- [ ] **Step 6: Apply to production, then re-inventory**

Only after Steps 2–5 pass and the owner has approved.

Run: `DATABASE_URL="<production url>" alembic upgrade head`
Then: `DATABASE_URL="<production url>" python -m scripts.db_inventory | tee docs/audit/db-inventory-after.txt`
Expected: identical row counts, revision now `s9t0u1v2w3x4`.

- [ ] **Step 7: Commit the evidence**

```bash
git add docs/audit/db-inventory-after.txt
git commit -m "chore(db): record production state after the auth migration"
```

### Task 1.6: Unify the settings layer (fixes D2)

**Files:** Create `src/tradelens/settings_source.py`; modify `services/password_reset.py:78`, `ui/components/auth.py:169`; test `tests/test_settings_source.py`

**Interfaces:** Produces `read_setting(name: str, default: str = "") -> str`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_settings_source.py
from src.tradelens import settings_source


def test_environment_wins_over_the_default(monkeypatch):
    monkeypatch.setenv("TRADELENS_TEST_KEY", "from-env")
    assert settings_source.read_setting("TRADELENS_TEST_KEY", "fallback") == "from-env"


def test_missing_setting_falls_back_to_the_default(monkeypatch):
    monkeypatch.delenv("TRADELENS_TEST_KEY", raising=False)
    assert settings_source.read_setting("TRADELENS_TEST_KEY", "fallback") == "fallback"


def test_reset_and_auth_agree_on_the_session_secret(monkeypatch):
    """D2: the two modules derived different secrets from one setting on Cloud.

    password_reset used os.getenv only; auth also consulted st.secrets. On
    Streamlit Cloud, where secrets are not in the environment, that meant reset
    tokens were signed with a random per-process key while sessions were not.
    """
    monkeypatch.setenv("TRADELENS_SESSION_SECRET", "shared-secret-value")
    from src.tradelens.services import password_reset
    from src.tradelens.ui.components import auth

    assert password_reset._base_secret() == auth._session_secret()
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_settings_source.py -v`
Expected: FAIL — `ModuleNotFoundError: src.tradelens.settings_source`

- [ ] **Step 3: Write the module**

```python
# src/tradelens/settings_source.py
"""One accessor for every deployment setting.

Two modules previously disagreed about where settings live: auth.py consulted
st.secrets, password_reset.py did not. On Streamlit Cloud — where secrets are
exposed through st.secrets and NOT through the environment — that meant the two
derived different signing keys from the same nominal TRADELENS_SESSION_SECRET,
so a reset token and a session token were signed with unrelated material.

Resolution order is fixed and identical for every caller:
environment, then st.secrets, then the supplied default.

Values are returned, never logged.
"""

from __future__ import annotations

import os

SETTING_NAMES = (
    "DATABASE_URL",
    "TRADELENS_SESSION_SECRET",
    "TRADELENS_INVITE_CODE",
    "SIGNUP_MODE",
    "TRADELENS_SMTP_HOST",
    "TRADELENS_SMTP_PORT",
    "TRADELENS_SMTP_USER",
    "TRADELENS_SMTP_PASSWORD",
    "TRADELENS_SMTP_FROM",
    "APP_ORIGIN",
    "SITE_ORIGIN",
)


def read_setting(name: str, default: str = "") -> str:
    """Resolve one setting: environment, then st.secrets, then the default."""
    value = os.getenv(name)
    if value:
        return str(value)
    try:
        import streamlit as st

        secret = st.secrets.get(name, None)
        if secret:
            return str(secret)
    except Exception:  # noqa: BLE001 — no secrets file is normal off-Cloud
        pass
    return default
```

- [ ] **Step 4: Repoint both modules**

In `services/password_reset.py`, replace the `_read_env` body (line 78) with a delegation, keeping the name so its call sites are untouched:

```python
def _read_env(name: str, default: str = "") -> str:
    from src.tradelens.settings_source import read_setting

    return read_setting(name, default)
```

In `ui/components/auth.py`, replace the `_read_secret` body (line 169) the same way.

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_settings_source.py tests/test_auth.py -v`
Expected: PASS, including the pre-existing auth tests.

- [ ] **Step 6: Full gate**

Run: `pytest tests/ -v --tb=short && ruff check src/ scripts/ && black --check src/ scripts/`
Expected: 136+ passing, 0 violations.

- [ ] **Step 7: Commit**

```bash
git add src/tradelens/settings_source.py src/tradelens/services/password_reset.py src/tradelens/ui/components/auth.py tests/test_settings_source.py
git commit -m "fix(config): one settings accessor so auth and reset share a secret"
```

**Phase 1 exit criteria:** production migrated, row counts identical, backfill verified against real data, downgrade executed successfully at least once, settings layer unified, full gate green.

---

# PHASE 2 — Next.js scaffold preserving the marketing site

**Files:** Create `web/package.json`, `web/tsconfig.json`, `web/tailwind.config.ts`, `web/next.config.js`, `web/app/layout.tsx`, `web/lib/utils.ts`, `web/scripts/build-marketing.mjs`, `web/.env.example`; modify `vercel.json`; delete `scripts/build_site.py` (Task 2.4 only); test `web/__tests__/marketing-preserved.test.ts`

**Interfaces:** Produces `cn()` from `web/lib/utils.ts`; Tailwind theme tokens `bg`, `surface`, `surface-2`, `border`, `text`, `muted`, `accent`; `buildMarketing(siteDir, outDir, {siteOrigin, appOrigin})`

### Task 2.1 — Scaffold
Next.js App Router + TypeScript + Tailwind + shadcn structure, `components/ui/` present. Tailwind theme extended with the exact spec §5 tokens. Fonts wired: Schibsted Grotesk, Satoshi, JetBrains Mono.

### Task 2.2 — Port the marketing build
`build-marketing.mjs` reproduces `scripts/build_site.py`: substitutes `__SITE_ORIGIN__` and `__APP_ORIGIN__`, **including its `validate_origin` checks** (they reject non-https and malformed origins — security-relevant, not cosmetic), copying `site/` → `web/public/`. Wired as `prebuild`.

**Tests:** substitution correctness; `validate_origin` rejects `http://`, a bare hostname, and an origin with a path; output for known inputs is byte-identical to `build_site.py`'s (run both, diff) — this is the regression guard, and it runs before `build_site.py` is deleted.

### Task 2.3 — Serve the site at `/`
`next.config.js` rewrite `/` → `/index.html`. Test asserts `/` returns the marketing HTML and that `site/index.html`'s six `[data-app-link]` CTAs are still present and still point at `APP_ORIGIN` (unchanged until Phase 7).

### Task 2.4 — Vercel cutover
`vercel.json` updated for the Next build; Root Directory set to `web/` in project settings (owner action — document it). Delete `scripts/build_site.py` **only after** the byte-identical test in 2.2 passes, so the substitution logic has one implementation.

**Exit:** `tradelensai.io/` renders the existing site unchanged; `/login` returns a 404 placeholder route; Python gate still green.

---

# PHASE 3 — 21.dev components, TradeLens theme

**Files:** Create `web/components/ui/sign-in-card-2.tsx`, `web/components/ui/password-strength.tsx`, `web/components/ui/input.tsx`, `web/app/login/page.tsx`, `web/app/signup/page.tsx`; test `web/__tests__/{sign-in-card,password-strength,signup-form}.test.tsx`

**Interfaces:** Produces `<SignInCard onSubmit={(identifier, password) => Promise<void>} error?: string />`; `<PasswordStrength value={string} />`; `usePasswordStrength(value) → {score, max, label, rules, guessable}`

### Task 3.1 — Sign-in card
Component in verbatim, then exactly the three spec §5 changes: branding, theme retarget, wiring. **Do not simplify any animation.** Preserve the 3D tilt, all four travelling beams with their delays, corner glows, glass card, background motion, input transitions, loading state.

**Tests:** all four beam elements render; tilt transform responds to mouse position; loading state swaps the label for the spinner and disables submit; the field is labelled "Email or username"; `prefers-reduced-motion` is respected; renders at 375px and 1280px.

### Task 3.2 — Password strength
Component in unmodified but for the tone palette. **Tests:** each rule fires on the right input; `"Password1!"` is flagged commonly-guessed; `"aaaa"` trips the run detector; `"abcd"` trips the sequence detector; meter has correct ARIA (`role="meter"`, `aria-valuenow`, `aria-valuetext`); the announcement is debounced.

### Task 3.3 — Signup form
All spec §12 fields; the eight referral options; `referral_source_other` appears only on "Other"; the invite field renders only when the server passes `signupMode === "invite"`.

**Tests:** "Other" reveals the field and nothing else does; invite field absent from the DOM in `open` mode (asserted on the DOM, not on CSS); client validation matches the server policy exactly.

**Exit:** `/login` and `/signup` render, animate, and validate. No network calls yet.

---

# PHASE 4 — Serverless auth

**Files:** Create `web/lib/db.ts`, `web/lib/password.ts`, `web/lib/identity.ts`, `web/lib/signup-mode.ts`, `web/lib/rate-limit.ts`, `web/lib/mail.ts`, `web/lib/verify-token.ts`, `web/app/api/auth/{login,signup,verify,resend,forgot,reset}/route.ts`; test `web/__tests__/api/*.test.ts`

**Interfaces:**
- `resolveIdentity(identifier: string): Promise<User | null>` — `@` → email only, else username only, **no fallback**
- `checkPolicy(password: string): {ok: boolean, reason?: string}` — the same rules the meter shows, enforced independently
- `signupMode(): "invite" | "open" | "closed"` — unrecognised → `"closed"`
- `rateLimit(bucket, action, limit, windowSec): Promise<boolean>`; `clearFailures(bucket, action)`
- `sendMail({to, subject, text}): Promise<void>` — throws when unconfigured
- `issueVerificationCode(user)` / `redeemVerificationCode(code)` — signing key includes `|verify-email|`, distinct from reset's `|reset|`

**Tests:** every spec §11 limit; failures-only counting; **success clears the identifier's counter**; all four `SIGNUP_MODE` values including an unrecognised one failing shut; server-side policy rejects a weak password submitted with the browser bypassed; duplicate email; generated-username collision under concurrency; a verification code replayed after use fails; a reset code replayed into the verify endpoint fails (purpose binding); expired codes fail; unconfigured SMTP returns a clear error **and leaves `email_verified_at` NULL**; identical response for registered and unregistered addresses on forgot-password.

**Exit:** signup → verification email → verified account, end to end against a real inbox on a Vercel preview.

---

# PHASE 5 — Handoff, durable session, real logout

**Files:** Create `web/lib/handoff.ts`, `web/lib/session-token.ts`, `src/tradelens/services/auth_sessions.py`, `src/tradelens/services/auth_handoff.py`; modify `ui/components/auth.py` (`require_auth`, `sign_out`); test `tests/test_auth_handoff.py`, `tests/test_auth_sessions.py`, `tests/test_cross_language_tokens.py`, `web/__tests__/token-compat.test.ts`

**Interfaces:**
- Python: `issue_handoff(user_id) -> str`, `redeem_handoff(token) -> int | None`, `open_session(user_id) -> str`, `restore_session(token) -> int | None`, `revoke_session(token) -> None`
- Node: `issueHandoff(userId): Promise<string>`, `issueLegacyToken(username, userId): string`

### Task 5.1: Cross-language token compatibility (do this first)

This is the seam where a silent mistake costs the most, so it is proven before anything depends on it.

- [ ] **Step 1: Write the failing Python-side fixture generator**

```python
# tests/test_cross_language_tokens.py
import json
import subprocess
import time
from pathlib import Path

from src.tradelens.ui.components import auth

FIXTURES = Path(__file__).parent / "fixtures" / "tokens.json"


def test_python_emits_padded_urlsafe_base64(monkeypatch):
    """Python's urlsafe_b64decode REQUIRES padding; Node's base64url strips it.

    If the Node implementation omits '=', Python raises on decode and every
    handoff fails with a signature that looked fine.
    """
    monkeypatch.setenv("TRADELENS_SESSION_SECRET", "test-secret")
    raw, _, _ = auth._issue_token("ayoub", 1).rpartition(".")
    assert len(raw) % 4 == 0, "payload must carry base64 padding"


def test_python_verifies_a_node_generated_token(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADELENS_SESSION_SECRET", "test-secret")
    result = subprocess.run(
        ["node", "web/scripts/emit-token.mjs", "ayoub", "1"],
        capture_output=True, text=True, check=True,
        env={"TRADELENS_SESSION_SECRET": "test-secret", "PATH": "/usr/bin:/bin"},
    )
    assert auth._verify_token(result.stdout.strip()) == ("ayoub", 1)


def test_python_rejects_a_tampered_node_token(monkeypatch):
    monkeypatch.setenv("TRADELENS_SESSION_SECRET", "test-secret")
    token = auth._issue_token("ayoub", 1)
    raw, _, sig = token.rpartition(".")
    assert auth._verify_token(f"{raw}.{sig[:-1]}0") is None


def test_python_rejects_an_expired_token(monkeypatch):
    monkeypatch.setenv("TRADELENS_SESSION_SECRET", "test-secret")
    token = auth._issue_token("ayoub", 1, now=time.time() - 90000)
    assert auth._verify_token(token) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_cross_language_tokens.py -v`
Expected: FAIL — `web/scripts/emit-token.mjs` does not exist.

- [ ] **Step 3: Write the Node token module and CLI**

```javascript
// web/lib/session-token.ts  (emit-token.mjs is a thin CLI wrapper over this)
import { createHmac } from "node:crypto";

const TTL_S = 24 * 3600;

/** Reproduce Python's token bytes exactly.
 *
 * Two details are load-bearing:
 *  - key order u, i, e — Python builds the dict in that order and signs the
 *    serialised string, so a reordered object produces a different signature.
 *  - '=' padding is KEPT. Node's "base64url" strips it; Python's
 *    urlsafe_b64decode raises without it.
 */
export function issueLegacyToken(username: string, userId: number | null,
                                 now = Date.now() / 1000): string {
  const payload = JSON.stringify({ u: username, i: userId, e: Math.floor(now + TTL_S) });
  const raw = Buffer.from(payload).toString("base64")
    .replace(/\+/g, "-").replace(/\//g, "_");   // urlsafe, padding retained
  const sig = createHmac("sha256", process.env.TRADELENS_SESSION_SECRET!)
    .update(raw).digest("hex");
  return `${raw}.${sig}`;
}
```

- [ ] **Step 4: Run both suites**

Run: `pytest tests/test_cross_language_tokens.py -v && npm --prefix web test token-compat`
Expected: PASS both directions.

- [ ] **Step 5: Commit**

```bash
git add web/lib/session-token.ts web/scripts/emit-token.mjs tests/test_cross_language_tokens.py web/__tests__/token-compat.test.ts
git commit -m "test(auth): prove Node and Python agree on token bytes"
```

### Task 5.2 — Handoff issue and redeem
120s TTL, SHA-256 at rest. Redemption is the single conditional UPDATE from spec §7.1 — **never read-then-write**.

**Tests:** valid redeem returns the user id; a second redeem returns `None`; expired returns `None`; unknown hash returns `None`; **two concurrent redemptions of the same token — exactly one succeeds** (threads against a real Postgres, not SQLite, since this is testing row-level atomicity).

### Task 5.3 — Server-side sessions, transport, and real logout

Implements spec §7.4. The session credential is a **new, independent** 256-bit
value — never the handoff token — carried in query parameter **`s`**.

```python
# src/tradelens/services/auth_sessions.py  (no Streamlit imports)
_IDLE_S = 8 * 3600
_ABSOLUTE_S = 12 * 3600

def open_session(user_id: int) -> str:
    """Mint a session credential. Returns the raw token; stores only its hash.

    32 bytes = 256 bits. The token carries no username, id, email, or expiry —
    it is an opaque lookup key, worthless without the row it points at.
    """
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    # expires_at is written once here and updated by nothing, which is what
    # makes the 12h cap absolute rather than merely nominal.
    ...  # INSERT sha256(token), user_id, now, now + _ABSOLUTE_S, now
    return token

def restore_session(token) -> int | None:
    """Resolve a credential to a user id, sliding the idle window.

    Fails closed on all three conditions. The idle window slides; the absolute
    bound does not, so an always-active session still dies at 12 hours.
    """
    ...  # SELECT ... WHERE token_hash = :h
         #   AND revoked_at IS NULL
         #   AND expires_at > now
         #   AND last_seen_at > now - _IDLE_S
         # then UPDATE last_seen_at = now   (never expires_at)
```

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_auth_sessions.py
def test_the_session_credential_is_not_the_handoff_token():
    handoff = auth_handoff.issue_handoff(user_id=1)
    session = auth_sessions.open_session(user_id=1)
    assert session != handoff
    assert auth_sessions.restore_session(handoff) is None, "a handoff must never resolve as a session"

def test_only_the_hash_is_stored():
    token = auth_sessions.open_session(user_id=1)
    rows = db.execute(text("SELECT token_hash FROM auth_sessions")).scalars().all()
    assert token not in rows
    assert rows[0] == hashlib.sha256(token.encode()).hexdigest()
    assert len(base64.urlsafe_b64decode(token + "==")) >= 32, "256 bits minimum"

def test_idle_window_slides_but_the_absolute_cap_does_not(frozen):
    token = auth_sessions.open_session(user_id=1)
    original_expiry = _expiry_of(token)
    for _ in range(11):                       # eleven hours of hourly activity
        frozen.tick(hours=1)
        assert auth_sessions.restore_session(token) == 1
    assert _expiry_of(token) == original_expiry, "activity must not extend the 12h cap"
    frozen.tick(hours=1)
    assert auth_sessions.restore_session(token) is None, "12h absolute cap"

def test_idle_expiry(frozen):
    token = auth_sessions.open_session(user_id=1)
    frozen.tick(hours=8, minutes=1)
    assert auth_sessions.restore_session(token) is None

def test_logout_revokes_the_row_not_just_the_url():
    """Defect D1. Popping the parameter left a working credential behind."""
    token = auth_sessions.open_session(user_id=1)
    auth_sessions.revoke_session(token)
    assert auth_sessions.restore_session(token) is None

def test_concurrent_restores_both_succeed_without_corrupting_last_seen():
    token = auth_sessions.open_session(user_id=1)
    results = run_in_threads(lambda: auth_sessions.restore_session(token), n=8)
    assert results == [1] * 8

def test_the_raw_credential_never_reaches_the_logs(caplog):
    caplog.set_level(logging.DEBUG)
    token = auth_sessions.open_session(user_id=1)
    auth_sessions.restore_session(token)
    auth_sessions.revoke_session(token)
    assert token not in caplog.text
```

- [ ] **Step 2:** Run — expect FAIL (`auth_sessions` does not exist).
- [ ] **Step 3:** Implement `open_session`, `restore_session`, `revoke_session`.
- [ ] **Step 4:** Run — expect PASS.
- [ ] **Step 5:** Commit.

### Task 5.4 — Wire transport into `require_auth()`

Resolution order, first match wins: `?s=` session → `?ht=` redeem → legacy
`?auth=` (kept until Phase 9) → login screen.

`_persist_session(st)` re-asserts `s` on **every** run, because Streamlit
navigation does not reliably preserve query parameters across page switches —
the same reason the existing `_persist_token` runs every execution.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_session_transport.py
def test_redeeming_ht_writes_s_and_removes_ht(st):
    st.query_params["ht"] = auth_handoff.issue_handoff(user_id=1)
    auth.require_auth()
    assert "ht" not in st.query_params, "the one-time credential must not linger"
    assert st.query_params["s"], "the session credential must be written"
    assert st.query_params["s"] != _the_handoff

def test_full_refresh_restores_the_session(st):
    """A refresh wipes session_state; only the URL survives."""
    token = auth_sessions.open_session(user_id=1)
    st.query_params["s"] = token
    st.session_state.clear()
    auth.require_auth()
    assert auth.is_authenticated()

def test_navigation_reasserts_s_when_streamlit_drops_it(st):
    token = auth_sessions.open_session(user_id=1)
    st.session_state[auth._SESSION_KEY] = token
    del st.query_params["s"]          # what a page switch can do
    auth.require_auth()
    assert st.query_params["s"] == token

def test_a_second_tab_shares_the_same_session(st_a, st_b):
    token = auth_sessions.open_session(user_id=1)
    for st in (st_a, st_b):
        st.query_params["s"] = token
        auth.require_auth()
        assert auth.is_authenticated()

def test_a_copied_url_authenticates_until_revoked(st_a, st_b):
    """The accepted beta limitation, asserted rather than glossed over.

    Community Cloud gives us no cookie write, so the durable credential rides
    in the URL and anyone holding it is signed in. Documented in spec 7.4 and
    removed by the OIDC end-state, not by this test passing.
    """
    token = auth_sessions.open_session(user_id=1)
    st_b.query_params["s"] = token            # pasted into a different browser
    auth.require_auth()
    assert auth.is_authenticated()
    auth_sessions.revoke_session(token)
    st_b.session_state.clear()
    auth.require_auth()
    assert not auth.is_authenticated()

def test_a_stale_credential_is_stripped_and_routed_to_login(st):
    token = auth_sessions.open_session(user_id=1)
    auth_sessions.revoke_session(token)
    st.query_params["s"] = token
    auth.require_auth()
    assert not auth.is_authenticated()
    assert "s" not in st.query_params, "a dead credential must not linger in the URL"
    # fails closed, routed to login, does not raise

def test_logout_revokes_and_clears(st):
    token = auth_sessions.open_session(user_id=1)
    st.query_params["s"] = token
    auth.require_auth()
    auth.sign_out(rerun=False)
    assert "s" not in st.query_params
    assert auth_sessions.restore_session(token) is None

def test_every_outbound_link_blocks_referrer_leakage():
    """An external link would send the full URL — session credential included —
    to SITE_ORIGIN in the Referer header."""
    html = auth_screen.compliance_html() + sidebar.render_footer_html()
    for anchor in re.findall(r"<a\s[^>]*href=\"https?://[^\"]+\"[^>]*>", html):
        assert "noreferrer" in anchor, f"external link leaks the session URL: {anchor}"
```

- [ ] **Step 2:** Run — expect FAIL.
- [ ] **Step 3:** Implement the resolution order, `_persist_session`, stale-param
      stripping, `sign_out` revocation, and `rel="noreferrer noopener"` on every
      external anchor.
- [ ] **Step 4:** Run — expect PASS.
- [ ] **Step 5:** Commit.

**Exit:** site login lands in Streamlit signed in; refresh keeps the session; sign-out genuinely revokes.

---

# PHASE 6 — Streamlit first-run Strategy Profile

**Files:** Create `src/tradelens/ui/components/strategy_onboarding.py`; modify `services/users.py`, `ui/components/auth.py` (`require_auth`); test `tests/test_strategy_onboarding.py`

**Interfaces:** `get_onboarding_state(user_id) -> {"onboarding_completed": bool, "strategy_profile_completed": bool}`; `mark_strategy_profile_completed(user_id) -> None`; `render_strategy_onboarding() -> None`

Copy exactly: **"Welcome to TradeLens"** / **"Before we analyze your trades, tell the AI how you trade."** Both exits set the flag; the skip exit writes **no** `Strategy` row — a fabricated profile would poison the AI context that profile data feeds.

**Tests:** gate fires when the flag is false; **skipped when `user_id is None`** (bootstrap sessions — `_require_concrete_user_id` raises on a null id); Save writes through `upsert_strategy_profile` and sets the flag; Skip sets the flag and creates no row; the gate does not re-trigger; no page can be reached around it (parametrised over every page module); no Streamlit import entered `services/`.

**Exit:** both first-run paths work; existing users with a profile never see it.

---

# PHASE 7 — CTA cutover

**Files:** modify `site/index.html` (6 `[data-app-link]` anchors: lines 63, 86, 276, 333, 337)

Repoint from `__APP_ORIGIN__` to `/login`. One commit, revertible in one commit. Keep `data-cta-location` attributes so analytics continues to distinguish nav/hero/pricing/final/mobile.

**Tests:** every CTA resolves to `/login`; no `__APP_ORIGIN__` token remains unsubstituted in built output; the marketing page is otherwise byte-identical to the previous build.

---

# PHASE 8 — Production verification

Run the full matrix against production and record results in `docs/audit/phase8-verification.md`. Each line is pass/fail with evidence.

**Auth:** legacy username login · email login · new signup · invite mode · open mode · closed mode · unrecognised `SIGNUP_MODE` fails shut · duplicate email · generated-username collision · weak password rejected server-side
**Email:** verification delivered · verification succeeds · expired verification · verification replay · reset delivered · reset succeeds · expired reset · reset code rejected by the verify endpoint
**Throttling:** login throttle · signup throttle · forgot throttle · success clears the failure counter
**Handoff/session:** one-time handoff · expired handoff · handoff replay · concurrent redemption · browser refresh · navigation across all Streamlit pages · logout revokes · revoked session cannot resume
**Onboarding:** existing user with profile skips · existing user without profile sees it once · new user completes it · new user chooses "I don't have a defined strategy yet"
**Regression:** marketing site unchanged · mobile auth UI at 375px · reduced-motion · 136+ tests green · 0 ruff violations

**Exit:** every line passes, or a failure is fixed and the matrix re-run.

---

# PHASE 9 — Deprecate the old paths

**Only after Phase 8 passes and a soak period the owner declares over.**

Remove: the Streamlit login screen render path in `auth_screen.py`; the legacy `?auth=` token functions in `auth.py`; the Streamlit-side reset panel. Then re-evaluate `TRADELENS_USERNAME`/`TRADELENS_PASSWORD` — if Task 1.1 confirmed `users > 0`, the path is already unreachable and removing it changes no behaviour. **Removal is a separate commit from everything else, and the secrets stay set in Streamlit Cloud until the owner removes them.**

**Tests:** the full suite still passes with the legacy paths gone; a stale `?auth=` URL fails closed rather than erroring.

---

## Self-review

**Spec coverage.** §4→Phase 2; §5→Phase 3; §6→Phases 3–4; §7.1→Phase 5.2; §7.2→Phase 5.3; §7.3→Phase 5.1; §8→Phase 1; §9.1–9.3→Phase 4; §9.4→Phase 6; §10→Phase 1 Gate + Task 1.5; §11→Phase 4; §12→Task 1.6 + Phase 1 Gate; §13→no change, asserted in Phase 4 (no Anthropic key on Vercel); §14→Phase 7; §15→throughout + Phase 8.

**Known gaps, deliberate.** Phases 2–9 carry task, file, interface, and test detail but not 5-minute step detail; each phase expands to steps at its start, when the preceding phase's actual interfaces are known rather than guessed. Spec §7.2 Option B (Streamlit native OIDC) is explicitly *not* in this plan — it is recorded as the end-state and needs its own spec.

**Type consistency checked.** `read_setting`, `resolveIdentity`, `signupMode`, `rateLimit`/`clearFailures`, `issue_handoff`/`redeem_handoff`, `open_session`/`restore_session`/`revoke_session`, `get_onboarding_state`/`mark_strategy_profile_completed`, `issueLegacyToken` are each named identically everywhere they appear.
