"""Find trades whose stored outcome disagrees with their stored P&L.

Write-time validation blocks new contradictions and the metrics engine
reads old ones coherently, but neither answers the operator's question:
*are any actually stored?* The beta scorecard requires that count to be
zero before charging anyone, so it has to be measurable.

Reporting is read-only by default. Legacy rows are never silently
rewritten — a repair happens only when explicitly requested, and reports
exactly what it changed.

    python scripts/audit_contradictions.py
    python scripts/audit_contradictions.py --repair
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.tradelens.db.models import Trade  # noqa: E402
from src.tradelens.db.session import SessionLocal  # noqa: E402
from src.tradelens.services.trade_validation import (  # noqa: E402
    OutcomeMismatch,
    canonical_outcome,
)


@dataclass(frozen=True)
class Contradiction:
    trade_id: int
    user_id: Optional[int]
    trade_date: Optional[str]
    asset: Optional[str]
    stored_result: Optional[str]
    pnl: Optional[float]
    expected_result: str


def find_contradictions() -> List[Contradiction]:
    """Every stored row whose label the money does not support. Read-only."""
    db = SessionLocal()
    try:
        found: List[Contradiction] = []
        for trade in db.query(Trade).all():
            try:
                canonical_outcome(trade.result, trade.pnl)
            except OutcomeMismatch:
                # Recompute from P&L alone to name the label it should carry.
                expected = canonical_outcome(None, trade.pnl)
                found.append(
                    Contradiction(
                        trade_id=trade.id,
                        user_id=trade.user_id,
                        trade_date=trade.trade_date,
                        asset=trade.asset,
                        stored_result=trade.result,
                        pnl=float(trade.pnl),
                        expected_result=str(expected),
                    )
                )
            except ValueError:
                # An unrecognised label is a different defect; not a
                # contradiction between two present values.
                continue
        return found
    finally:
        db.close()


def repair_contradictions() -> int:
    """Set each contradictory label to the one its P&L supports.

    Deliberately separate from the audit: P&L is the fact, so the label is
    what gives, but a trader's record is not edited without being asked.
    """
    targets = find_contradictions()
    if not targets:
        return 0

    db = SessionLocal()
    try:
        changed = 0
        for item in targets:
            trade = db.query(Trade).filter(Trade.id == item.trade_id).first()
            if trade is None:  # pragma: no cover — read moments ago
                continue
            trade.result = item.expected_result
            changed += 1
        db.commit()
        return changed
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def format_report(found: List[Contradiction]) -> str:
    if not found:
        return "No contradictory records. Stored outcomes all match their P&L."

    lines = [
        f"{len(found)} contradictory record(s) found.",
        "",
        "| Trade | Owner | Date | Asset | Stored | P&L | Should be |",
        "|---:|---:|---|---|---|---:|---|",
    ]
    for item in found:
        owner = "—" if item.user_id is None else str(item.user_id)
        lines.append(
            f"| {item.trade_id} | {owner} | {item.trade_date or '—'} | "
            f"{item.asset or '—'} | {item.stored_result} | "
            f"{item.pnl:,.2f} | {item.expected_result} |"
        )
    lines += [
        "",
        "These predate write-time validation. Metrics already read them by "
        "P&L, so dashboards are correct; the stored label is what is stale.",
        "Run with --repair to set each label to the one its P&L supports.",
    ]
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repair",
        action="store_true",
        help="rewrite each contradictory label to match its P&L",
    )
    args = parser.parse_args(argv)

    found = find_contradictions()
    print(format_report(found))

    if args.repair and found:
        changed = repair_contradictions()
        print(f"\nRepaired {changed} record(s).")
        remaining = find_contradictions()
        print(f"Remaining contradictions: {len(remaining)}")
        return 1 if remaining else 0

    # Non-zero when contradictions exist, so this can gate a release check.
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
