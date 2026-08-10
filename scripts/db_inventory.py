"""Read-only census of a TradeLens database.

Run before and after a migration; every count must match for every table the
migration is not supposed to change. Prints counts and schema facts only —
never row contents, never a connection string, never a credential.

Usage:
    DATABASE_URL="<url>" python -m scripts.db_inventory
    DATABASE_URL="<url>" python -m scripts.db_inventory > docs/audit/db-inventory-before.txt

Two things this script must survive, both confirmed against production on
2026-08-10:

* **No ``alembic_version`` table.** Production was initialised with
  ``init_db()`` (``Base.metadata.create_all``), which builds the schema without
  ever writing an Alembic revision. Reporting UNTRACKED is the correct answer,
  not a crash.
* **The AI analysis table is ``aianalysis``**, not ``ai_analyses``. The model
  has always said so; the earlier guess in this script did not.

The bootstrap-login line answers a specific question. TRADELENS_USERNAME /
TRADELENS_PASSWORD are only ever consulted when the users table is empty (see
ui/components/auth.py:298), so once a single account exists that path is
already unreachable and the secrets are inert.
"""

from __future__ import annotations

from sqlalchemy import inspect, text

from src.tradelens.db.session import SessionLocal, engine

# Table names taken from models.py __tablename__ declarations, not guessed.
TABLES = (
    "users",
    "user_settings",
    "strategies",
    "trades",
    "screenshots",
    "aianalysis",
    "corrections",
    "ai_usage_log",
    "performance_metrics",
    "weekly_reviews",
)

SITE_AUTH_TABLES = ("auth_handoffs", "auth_sessions", "auth_attempts")


def _revision(db, present: set) -> str:
    """The tracked Alembic revision, or an explicit UNTRACKED marker.

    A missing alembic_version table is a real and important state, not an
    error: it means the schema was built by create_all rather than by
    migrations, so nothing may be stamped until the schema is proven
    equivalent to the revision being claimed.
    """
    if "alembic_version" not in present:
        return "UNTRACKED / alembic_version missing"
    try:
        value = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception as exc:  # noqa: BLE001 — type name only, never the message
        return f"UNREADABLE ({type(exc).__name__})"
    return str(value) if value else "EMPTY / alembic_version has no row"


def _count(db, name: str):
    try:
        return db.execute(text(f"SELECT count(*) FROM {name}")).scalar()  # noqa: S608
    except Exception as exc:  # noqa: BLE001
        return f"ERROR ({type(exc).__name__})"


def main() -> None:
    inspector = inspect(engine)
    present = set(inspector.get_table_names())
    db = SessionLocal()
    try:
        print(f"alembic revision: {_revision(db, present)}")
        print(f"dialect:          {engine.dialect.name}")
        print(f"tables present:   {len(present)}")
        print()

        print("row counts")
        for name in TABLES:
            if name not in present:
                print(f"  {name:22} MISSING")
                continue
            print(f"  {name:22} {_count(db, name)}")

        unexpected = present - set(TABLES) - set(SITE_AUTH_TABLES) - {"alembic_version"}
        if unexpected:
            print()
            print("tables not declared in models.py")
            for name in sorted(unexpected):
                print(f"  {name:22} {_count(db, name)}")

        print()
        print("migration inputs")
        if "users" in present:
            user_count = _count(db, "users")
            with_email = db.execute(
                text("SELECT count(*) FROM users WHERE email IS NOT NULL")
            ).scalar()
            print(f"  users with an email        {with_email}")
        else:
            user_count = 0
            print("  users table MISSING")

        if "strategies" in present:
            with_strategy = db.execute(
                text(
                    "SELECT count(DISTINCT user_id) FROM strategies "
                    "WHERE is_active = 1 AND user_id IS NOT NULL"
                )
            ).scalar()
            print(f"  users with active strategy {with_strategy}")
            print("    -> expected strategy_profile_completed = true after backfill")

        print()
        print("bootstrap credential path")
        print(f"  users table empty          {user_count == 0}")
        print(
            "  reachable in production    "
            f"{user_count == 0}   (TRADELENS_USERNAME/PASSWORD)"
        )

        print()
        print("users indexes (email uniqueness is known drift)")
        if "users" in present:
            for index in inspector.get_indexes("users"):
                flag = "UNIQUE" if index.get("unique") else "      "
                print(f"  {flag} {index['name']:24} {index.get('column_names')}")
            for constraint in inspector.get_unique_constraints("users"):
                print(
                    f"  UNIQUE {constraint['name'] or '(unnamed)':24} "
                    f"{constraint.get('column_names')}  [constraint]"
                )

        print()
        print("site-auth tables")
        for name in SITE_AUTH_TABLES:
            if name not in present:
                print(f"  {name:22} not yet created")
                continue
            print(f"  {name:22} {_count(db, name)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
