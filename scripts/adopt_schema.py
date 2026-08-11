"""Bring an UNTRACKED database to canonical schema state.

For the production-derived lineage, which has no ``alembic_version`` row and is
knowingly not equivalent to any revision. It cannot be migrated by Alembic
without first being stamped, and stamping it at r8s9t0u1v2w3 would assert
something false — its schema differs from r8 in 18 known ways.

So the reconciliation runs here instead, outside Alembic's revision bookkeeping,
using the same operations the ``t0u1v2w3x4y5`` revision applies to the tracked
lineage. Afterwards the database is compared against a reference built by
migrations to exactly that revision, and only if the comparison is empty is it
stamped — directly at ``t0u1v2w3x4y5``, an assertion that has by then been
demonstrated rather than assumed.

Usage:
    DATABASE_URL="<url>" python -m scripts.adopt_schema --dry-run
    DATABASE_URL="<url>" python -m scripts.adopt_schema --apply

Prints statements and counts only; never a connection string.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import inspect

from src.tradelens.db.schema_adoption import (
    AdoptionPrecheckFailed,
    adopt,
    plan,
    preflight,
)
from src.tradelens.db.session import engine


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--dry-run", action="store_true", help="show the plan, change nothing"
    )
    group.add_argument("--apply", action="store_true", help="execute the plan")
    args = parser.parse_args()

    if engine is None:
        print("database unavailable", file=sys.stderr)
        return 2

    with engine.begin() as conn:
        tracked = "alembic_version" in set(inspect(conn).get_table_names())
        print(f"dialect:        {conn.dialect.name}")
        print(f"alembic-tracked: {tracked}")
        if tracked:
            print(
                "\nREFUSING: this database is tracked by Alembic. Use "
                "`alembic upgrade` — reconciliation outside Alembic is only for "
                "the untracked lineage.",
                file=sys.stderr,
            )
            return 2

        print("\npre-checks")
        problems = preflight(conn)
        for problem in problems:
            print(f"  BLOCKED: {problem}")
        if not problems:
            print("  all clear")

        statements = plan(conn)
        print(f"\nplan ({len(statements)} statements)")
        for statement in statements:
            print(f"  {statement}")
        if not statements:
            print("  (already canonical)")

        if args.dry_run:
            print("\ndry run — nothing applied")
            return 1 if problems else 0

        if problems:
            print("\nnot applying: pre-checks failed", file=sys.stderr)
            return 2

        try:
            applied = adopt(conn)
        except AdoptionPrecheckFailed as exc:
            print(f"\npre-check failed: {exc}", file=sys.stderr)
            return 2

        print(f"\napplied {len(applied)} statements")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
