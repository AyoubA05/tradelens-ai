"""Read-only account state for the dev walkthrough. Never writes.

Prints the flags and derived facts an end-to-end run needs to assert, and
nothing that could be replayed: password hashes appear only as a short
fingerprint, tokens only as counts and timestamps. Point it at dev.
"""

from __future__ import annotations

import hashlib
import os
import sys

from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tradelens.db.session import SessionLocal  # noqa: E402


def fingerprint(value) -> str:
    """A stable, non-reversible label for a hash, so a run can prove it changed."""
    if not value:
        return "-"
    return hashlib.sha256(str(value).encode()).hexdigest()[:16]


def main() -> int:
    needle = sys.argv[1] if len(sys.argv) > 1 else None
    db = SessionLocal()
    try:
        rows = (
            db.execute(
                text(
                    """
                SELECT id, username, email, is_active, onboarding_completed,
                       strategy_profile_completed, email_verification_required,
                       email_verified_at, password_hash, full_name, birthday,
                       referral_source, referral_source_other
                  FROM users
                 WHERE (:needle IS NULL OR email LIKE :like)
                 ORDER BY id
                """
                ),
                {"needle": needle, "like": f"%{needle}%" if needle else "%"},
            )
            .mappings()
            .all()
        )

        for row in rows:
            print(f"user id={row['id']}")
            print(f"  username                    {row['username']}")
            print(f"  email                       {row['email']}")
            print(f"  full_name                   {row['full_name']}")
            print(f"  birthday                    {row['birthday']}")
            print(f"  referral_source             {row['referral_source']}")
            print(f"  referral_source_other       {row['referral_source_other']}")
            print(f"  is_active                   {row['is_active']}")
            print(f"  onboarding_completed        {row['onboarding_completed']}")
            print(f"  strategy_profile_completed  {row['strategy_profile_completed']}")
            print(f"  email_verification_required {row['email_verification_required']}")
            print(
                f"  email_verified_at           {'set' if row['email_verified_at'] else 'NULL'}"
            )
            print(f"  password_hash prefix        {str(row['password_hash'])[:7]}")
            print(f"  password_hash fingerprint   {fingerprint(row['password_hash'])}")

            for table, label in (
                ("auth_sessions", "sessions"),
                ("auth_handoffs", "handoffs"),
                ("email_verifications", "verifications"),
                ("password_resets", "resets"),
                ("strategies", "strategies"),
                ("trades", "trades"),
            ):
                if table == "auth_sessions":
                    detail = db.execute(
                        text(
                            "SELECT surface, count(*) FROM auth_sessions"
                            " WHERE user_id = :u AND revoked_at IS NULL"
                            " GROUP BY surface ORDER BY surface"
                        ),
                        {"u": row["id"]},
                    ).all()
                    print(f"  live sessions               {dict(detail) or '{}'}")
                    continue
                count = db.execute(
                    text(f"SELECT count(*) FROM {table} WHERE user_id = :u"),
                    {"u": row["id"]},
                ).scalar()
                print(f"  {label:<27} {count}")
            print()

        if needle is None:
            totals = db.execute(
                text(
                    "SELECT (SELECT count(*) FROM users) u,"
                    " (SELECT count(*) FROM auth_sessions) s,"
                    " (SELECT count(*) FROM auth_handoffs) h,"
                    " (SELECT count(*) FROM auth_attempts) a,"
                    " (SELECT count(*) FROM email_verifications) v,"
                    " (SELECT count(*) FROM password_resets) r"
                )
            ).one()
            print(
                f"totals users={totals[0]} sessions={totals[1]} handoffs={totals[2]}"
                f" attempts={totals[3]} verifications={totals[4]} resets={totals[5]}"
            )
    finally:
        db.close()
    return 0


def safe_main() -> int:
    """Run the inspection, and never let a driver message reach the terminal.

    Not defensive padding. Pointing this at production once produced a
    psycopg2 traceback that printed the database host into a transcript —
    SQLAlchemy inlines the URL in its own message and psycopg2 names the server
    in a connection error, so *any* uncaught failure here is a disclosure. The
    exception class name is the most that may be said, which is also enough to
    act on: OperationalError is a network problem, ProgrammingError is a bad
    query, and neither needs the host to be diagnosed.
    """
    try:
        return main()
    except BaseException as exc:  # noqa: BLE001 — see above; nothing re-raised
        print(f"inspect_account failed: {type(exc).__name__}")
        return 1


if __name__ == "__main__":
    raise SystemExit(safe_main())
