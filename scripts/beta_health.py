"""Aggregate-only health report for the private beta.

Knowing that 40% of accounts reach a first useful review is a product
decision. Knowing *which* trader didn't is surveillance the beta has no
need for, so this is aggregate by construction: only `user_id` is read
from the database, milestones are reduced to booleans and counts in
memory, and the output carries rates and totals only. No username, journal
prose, psychology text, strategy rule, screenshot, or P&L ever enters it.

    python scripts/beta_health.py --format markdown
    python scripts/beta_health.py --format json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# A weekly review only counts as activation on a sample worth reviewing.
TRADES_FOR_ACTIVATION = 5

_EMPTY = {
    "accounts": 0,
    "strategy_rate": 0.0,
    "first_trade_rate": 0.0,
    "five_trade_rate": 0.0,
    "first_review_rate": 0.0,
    "activation_rate": 0.0,
}


def compute_beta_health(
    users: pd.DataFrame,
    milestones: pd.DataFrame,
    *,
    as_of: date,
) -> dict[str, Any]:
    """Reduce per-user milestones to beta-wide rates.

    `as_of` is accepted so callers can pin a reporting date; the current
    metrics are cumulative and do not use it.
    """
    del as_of

    accounts = len(users)
    if accounts == 0:
        return dict(_EMPTY)

    # Left-join onto the user list: an account with no milestone row has
    # simply not started, and a stale milestone row for a deleted user must
    # not push a rate above 1.0.
    scoped = users[["user_id"]].merge(milestones, on="user_id", how="left")

    def flags(column: str) -> pd.Series:
        """Missing rows mean 'not started'. Compared against True rather than
        filled, to avoid pandas' deprecated object-dtype downcast."""
        series = scoped.get(column, pd.Series(dtype=object))
        return series.eq(True)

    trades = pd.to_numeric(
        scoped.get("complete_trades", pd.Series(dtype=float)), errors="coerce"
    ).fillna(0)

    has_strategy = flags("has_strategy")
    reviewed_bool = flags("has_review")
    five_trades = trades >= TRADES_FOR_ACTIVATION

    def ratio(series: pd.Series) -> float:
        return round(float(series.sum()) / accounts, 4)

    return {
        "accounts": accounts,
        "strategy_rate": ratio(has_strategy),
        "first_trade_rate": ratio(trades >= 1),
        "five_trade_rate": ratio(five_trades),
        "first_review_rate": ratio(reviewed_bool),
        "activation_rate": ratio(five_trades & reviewed_bool),
    }


_LABELS = (
    ("accounts", "Accounts"),
    ("strategy_rate", "Account → strategy"),
    ("first_trade_rate", "Account → first trade"),
    ("five_trade_rate", "Account → five trades"),
    ("first_review_rate", "Account → first review"),
    ("activation_rate", "Activated (five trades + review)"),
)


def format_markdown(report: dict[str, Any], *, as_of: date) -> str:
    lines = [
        f"# Beta health — {as_of.isoformat()}",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key, label in _LABELS:
        value = report[key]
        rendered = str(value) if key == "accounts" else f"{value * 100:.1f}%"
        lines.append(f"| {label} | {rendered} |")
    lines += ["", "Aggregate counts only. No per-user data is recorded here."]
    return "\n".join(lines)


def _load_from_database() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read only what the aggregate needs: ids, and derived milestone flags."""
    from src.tradelens.db.models import Strategy, Trade, User, WeeklyReview
    from src.tradelens.db.session import SessionLocal
    from src.tradelens.services.activation import is_complete_trade

    db = SessionLocal()
    try:
        user_ids = [row.id for row in db.query(User.id).all()]
        users = pd.DataFrame({"user_id": user_ids, "created_at": None})

        strategy_owners = {
            row.user_id
            for row in db.query(Strategy.user_id).filter(Strategy.is_active == 1).all()
        }
        reviewed = {row.user_id for row in db.query(WeeklyReview.user_id).all()}

        complete_counts: dict[Any, int] = {}
        for trade in db.query(Trade).all():
            if is_complete_trade(trade):
                complete_counts[trade.user_id] = (
                    complete_counts.get(trade.user_id, 0) + 1
                )

        milestones = pd.DataFrame(
            [
                {
                    "user_id": uid,
                    "has_strategy": uid in strategy_owners,
                    "complete_trades": complete_counts.get(uid, 0),
                    "has_review": uid in reviewed,
                }
                for uid in user_ids
            ]
        )
        return users, milestones
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args(argv)

    users, milestones = _load_from_database()
    today = date.today()
    report = compute_beta_health(users, milestones, as_of=today)

    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print(format_markdown(report, as_of=today))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
