#!/usr/bin/env python3
"""Assign NULL-owned legacy data to one existing user.

The default command is a dry run. Pass ``--apply`` only after reviewing the
reported rows and taking a database backup.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

# Allow this script to run directly from the repository checkout.
_ROOT = str(Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from sqlalchemy import update  # noqa: E402

from src.tradelens.db.models import (  # noqa: E402
    Correction,
    Strategy,
    Trade,
    User,
    WeeklyReview,
)
from src.tradelens.db.session import SessionLocal  # noqa: E402


@dataclass(frozen=True)
class AssignmentPlan:
    """The exact target and dry-run counts observed before an apply."""

    username: str
    user_id: int
    counts: dict[str, int]
    # Weeks where assigning would give the target two recaps: weekly_reviews
    # is unique per (user_id, week_start) (migration i5j6k7l8m9n0).
    weekly_conflicts: int = 0


_OWNED_TABLES = (
    ("trades", Trade),
    ("strategies", Strategy),
    ("weekly_reviews", WeeklyReview),
    ("corrections", Correction),
)


def plan_assignment(username: str) -> AssignmentPlan:
    """Resolve an exact username and count its currently unowned legacy rows."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).one_or_none()
        if user is None:
            raise ValueError(f"Unknown username: {username}")

        counts = {
            table_name: db.query(model).filter(model.user_id.is_(None)).count()
            for table_name, model in _OWNED_TABLES
        }
        return AssignmentPlan(
            username=username,
            user_id=user.id,
            counts=counts,
            weekly_conflicts=_weekly_conflicts(db, user.id),
        )
    finally:
        db.close()


def _weekly_conflicts(db, user_id: int) -> int:
    """Weeks whose ownerless recaps plus the target's own would exceed one."""
    per_week: dict[str, int] = {}
    for (week,) in db.query(WeeklyReview.week_start).filter(
        WeeklyReview.user_id.is_(None)
    ):
        per_week[week] = per_week.get(week, 0) + 1
    owned = {
        week
        for (week,) in db.query(WeeklyReview.week_start).filter(
            WeeklyReview.user_id == user_id
        )
    }
    return sum(1 for week, n in per_week.items() if n + (week in owned) > 1)


def apply_assignment(plan: AssignmentPlan) -> dict[str, int]:
    """Atomically assign rows that are still NULL-owned when this runs.

    Every update repeats the NULL-owner predicate instead of trusting the
    earlier plan, so a concurrently assigned row is never overwritten.
    """
    db = SessionLocal()
    try:
        with db.begin():
            changed = {}
            for table_name, model in _OWNED_TABLES:
                result = db.execute(
                    update(model)
                    .where(model.user_id.is_(None))
                    .values(user_id=plan.user_id)
                )
                changed[table_name] = result.rowcount or 0
        return changed
    finally:
        db.close()


def _print_plan(plan: AssignmentPlan) -> None:
    print(f"Target username: {plan.username}")
    print(f"Target user ID: {plan.user_id}")
    for table_name, count in plan.counts.items():
        print(f"{table_name}: {count}")
    print(f"weekly_reviews conflicts: {plan.weekly_conflicts} week(s)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Assign NULL-owned legacy data to an existing user."
    )
    parser.add_argument("--username", required=True, help="Exact existing username")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the assignment; omit for a safe dry run",
    )
    args = parser.parse_args(argv)

    try:
        plan = plan_assignment(args.username)
    except ValueError as exc:
        parser.error(str(exc))

    _print_plan(plan)
    if not args.apply:
        print("Dry run only; no rows were changed. Re-run with --apply after approval.")
        return 0

    if plan.weekly_conflicts:
        print(
            f"Refusing to apply: {plan.weekly_conflicts} week(s) would give "
            f"{plan.username} two weekly recaps. Resolve them deliberately first; "
            "nothing was changed."
        )
        return 1

    changed = apply_assignment(plan)
    print("Applied rows:")
    for table_name, count in changed.items():
        print(f"{table_name}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
