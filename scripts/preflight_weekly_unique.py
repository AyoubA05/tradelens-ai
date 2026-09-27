"""Read-only production preflight for migration i5j6k7l8m9n0.

Before the (user_id, week_start) unique constraint on `weekly_reviews` may be
deployed, run this against the target database. It counts duplicate groups and
reports each one (owner id, week, row count — never recap content). It changes
nothing: on PostgreSQL every statement runs inside a `READ ONLY` transaction,
so even a mistaken write would be refused by the server.

Exit codes: 0 no duplicates (deployment may proceed), 3 duplicates found (stop
the deployment; resolve them deliberately — never delete or auto-merge trader
data here), 2 the check could not run.

    DATABASE_URL=<target> python scripts/preflight_weekly_unique.py

The URL is read from the environment and never printed.
"""

from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine, text

_DUPLICATES = text(
    "SELECT user_id, week_start, COUNT(*) AS n FROM weekly_reviews"
    " WHERE user_id IS NOT NULL"
    " GROUP BY user_id, week_start HAVING COUNT(*) > 1"
    " ORDER BY user_id, week_start"
)


def find_duplicates(url: str) -> list[tuple[int, str, int]]:
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            if engine.dialect.name == "postgresql":
                connection.execute(text("SET TRANSACTION READ ONLY"))
            rows = connection.execute(_DUPLICATES).all()
            connection.rollback()  # nothing to keep, even on SQLite
        return [(int(u), str(w), int(n)) for u, w, n in rows]
    finally:
        engine.dispose()


def main() -> int:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        print("preflight: DATABASE_URL is not set", file=sys.stderr)
        return 2
    try:
        duplicates = find_duplicates(url)
    except Exception as exc:  # noqa: BLE001 — report the type, never the URL
        print(f"preflight: could not run ({type(exc).__name__})", file=sys.stderr)
        return 2
    if not duplicates:
        print(
            "preflight: 0 duplicate (user_id, week_start) groups — migration i5j6k7l8m9n0 may deploy"
        )
        return 0
    print(
        f"preflight: {len(duplicates)} duplicate (user_id, week_start) group(s) — "
        "STOP: do not deploy migration i5j6k7l8m9n0"
    )
    for user_id, week_start, n in duplicates:
        print(f"  user_id={user_id} week_start={week_start} rows={n}")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
