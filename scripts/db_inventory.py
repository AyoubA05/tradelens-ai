"""Read-only census of a TradeLens database.

Run before and after a migration; every count must match for every table the
migration is not supposed to change. Prints counts and schema facts only —
never row contents, never a connection string, never a credential.

Usage:
    DATABASE_URL="<url>" python -m scripts.db_inventory
    DATABASE_URL="<url>" python -m scripts.db_inventory > docs/audit/db-inventory-before.txt

The bootstrap-login line answers a specific question. TRADELENS_USERNAME /
TRADELENS_PASSWORD are only ever consulted when the users table is empty (see
ui/components/auth.py:298), so once a single account exists that path is
already unreachable and the secrets are inert.
"""

from __future__ import annotations

from sqlalchemy import inspect, text

from src.tradelens.db.session import SessionLocal, engine

TABLES = (
    "users",
    "trades",
    "strategies",
    "corrections",
    "weekly_reviews",
    "screenshots",
    "ai_analyses",
    "performance_metrics",
    "ai_usage_log",
)


def main() -> None:
    inspector = inspect(engine)
    present = set(inspector.get_table_names())
    db = SessionLocal()
    try:
        revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
        print(f"alembic revision: {revision}")
        print(f"dialect:          {engine.dialect.name}")
        print()

        print("row counts")
        for name in TABLES:
            if name not in present:
                print(f"  {name:22} MISSING")
                continue
            count = db.execute(
                text(f"SELECT count(*) FROM {name}")
            ).scalar()  # noqa: S608
            print(f"  {name:22} {count}")

        print()
        user_count = db.execute(text("SELECT count(*) FROM users")).scalar()
        with_email = db.execute(
            text("SELECT count(*) FROM users WHERE email IS NOT NULL")
        ).scalar()
        with_strategy = db.execute(
            text("SELECT count(DISTINCT user_id) FROM strategies WHERE is_active = 1")
        ).scalar()

        print("migration inputs")
        print(f"  users with an email        {with_email}")
        print(f"  users with active strategy {with_strategy}")
        print("    -> expected strategy_profile_completed = true after backfill")
        print()
        print("bootstrap credential path")
        print(f"  users table empty          {user_count == 0}")
        print(
            "  reachable in production    "
            f"{user_count == 0}   (TRADELENS_USERNAME/PASSWORD)"
        )

        # Present only after the migration; absent beforehand. Reported so the
        # before/after diff shows the new tables appearing and nothing else.
        print()
        print("site-auth tables")
        for name in ("auth_handoffs", "auth_sessions", "auth_attempts"):
            if name not in present:
                print(f"  {name:22} not yet created")
                continue
            count = db.execute(
                text(f"SELECT count(*) FROM {name}")
            ).scalar()  # noqa: S608
            print(f"  {name:22} {count}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
