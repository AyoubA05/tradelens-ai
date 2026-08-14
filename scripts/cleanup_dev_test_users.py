"""Remove disposable walkthrough accounts from dev and prove the state restored.

The Step 11 browser walkthrough creates accounts by hand, so unlike the
scripted integrations it has no ``finally`` of its own. This is that finally.

**What it will not touch.** Only accounts whose email matches the disposable
pattern are eligible, and ``ayoub``/``Ayoub`` are excluded by username as a
second, independent condition — one predicate protecting the two legacy rows
would be one predicate too few. It refuses outright if the run would delete an
account that does not match both.

Children before parents: seven of the foreign keys into ``users`` are
ON DELETE NO ACTION, so deleting a user with dependent rows fails rather than
cascading, and a half-finished cleanup is worse than none.
"""

from __future__ import annotations

import hashlib
import os
import sys

from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tradelens.db.session import SessionLocal  # noqa: E402

# Disposable accounts are created with these email prefixes and nothing else is.
DISPOSABLE_PREFIXES = ("s11.", "probe.", "probe2@")
PROTECTED_USERNAMES = ("ayoub", "Ayoub")

CHILD_TABLES = (
    "auth_sessions",
    "auth_handoffs",
    "email_verifications",
    "password_resets",
    "user_settings",
    "trades",
    "strategies",
    "corrections",
    "weekly_reviews",
    "ai_usage_log",
)


def main() -> int:
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                "SELECT id, username, email FROM users"
                " WHERE email IS NOT NULL AND username NOT IN :protected"
                " ORDER BY id"
            ),
            {"protected": PROTECTED_USERNAMES},
        ).all()

        targets = [
            (uid, username)
            for uid, username, email in rows
            if any(str(email).startswith(prefix) for prefix in DISPOSABLE_PREFIXES)
        ]

        if any(username in PROTECTED_USERNAMES for _, username in targets):
            print("REFUSING: a protected account matched the disposable pattern")
            return 1

        print(f"disposable accounts to remove: {[u for _, u in targets]}")
        ids = [uid for uid, _ in targets]

        if ids:
            for table in CHILD_TABLES:
                try:
                    result = db.execute(
                        text(f"DELETE FROM {table} WHERE user_id = ANY(:ids)"),
                        {"ids": ids},
                    )
                    if result.rowcount:
                        print(f"  {table}: {result.rowcount} row(s)")
                except Exception as exc:  # noqa: BLE001 — table may not exist
                    db.rollback()
                    print(f"  {table}: skipped ({type(exc).__name__})")
            db.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": ids})
            db.commit()

        # Attempt rows are keyed by hashed bucket, not user_id, so they cannot
        # be tied back to the deleted accounts and are cleared wholesale.
        swept = db.execute(text("DELETE FROM auth_attempts")).rowcount
        db.commit()
        print(f"  auth_attempts: {swept} row(s)")

        print("\nPOST-CLEANUP STATE")
        print(
            f"  users                {db.execute(text('SELECT count(*) FROM users')).scalar()}"
        )
        names = [
            r[0]
            for r in db.execute(text("SELECT username FROM users ORDER BY id")).all()
        ]
        print(f"  usernames            {names}")
        for table in (
            "auth_sessions",
            "auth_handoffs",
            "auth_attempts",
            "email_verifications",
            "password_resets",
        ):
            count = db.execute(text(f"SELECT count(*) FROM {table}")).scalar()
            print(f"  {table:<20} {count}")
        print(
            f"  trades               {db.execute(text('SELECT count(*) FROM trades')).scalar()}"
        )
        print(
            f"  strategies           "
            f"{db.execute(text('SELECT count(*) FROM strategies')).scalar()}"
        )
        for username in PROTECTED_USERNAMES:
            digest = db.execute(
                text("SELECT password_hash FROM users WHERE username = :n"),
                {"n": username},
            ).scalar()
            print(
                f"  {username} fingerprint    "
                f"{hashlib.sha256(str(digest).encode()).hexdigest()[:16]}"
            )

        ok = names == list(PROTECTED_USERNAMES)
        print("\n" + ("CLEANUP VERIFIED" if ok else "CLEANUP INCOMPLETE"))
        return 0 if ok else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
