"""User-scoped context assembly for the global AI Partner.

This module reads one authenticated trader's records and shapes them into
prompt text plus parallel evidence descriptors. It never calls a model and
never logs usage.

A ``PartnerEvidenceSource`` exists if and only if its record contributed a
line to ``context_text``. Budgets are applied while admitting both together;
the two representations are never trimmed independently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from sqlalchemy import func

from src.tradelens.db.models import Trade
from src.tradelens.db.session import SessionLocal
from src.tradelens.services.strategy import get_active_strategy

MAX_CONTEXT_CHARS = 12_000
MAX_EVIDENCE_SOURCES = 40
MAX_JOURNAL_ROWS = 15
MAX_TRADE_ROWS = 24

JOURNAL_HEADING = "## Journal notes"
TRADES_HEADING = "## Completed trades"
STRATEGY_HEADING = "## Active strategy profile"


@dataclass(frozen=True)
class PartnerEvidenceSource:
    """One owned record that contributed to the assembled context."""

    kind: str
    record_id: int
    user_id: int
    label: str
    occurred_on: Optional[str] = None


@dataclass(frozen=True)
class PartnerContext:
    """Bounded context and the records from which it was assembled."""

    context_text: str
    strategy_profile: Optional[dict]
    evidence_sources: Tuple[PartnerEvidenceSource, ...]
    completed_trade_count: int
    journal_entry_count: int


@dataclass(frozen=True)
class _Candidate:
    heading: str
    line: str
    source: PartnerEvidenceSource


def _require_concrete_user_id(user_id: int) -> int:
    """Reject an ownerless read before any database session opens."""
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("user_id must be a positive integer")
    return user_id


def _one_line(value) -> str:
    """Collapse a stored value so it cannot create prompt structure."""
    return " ".join(str(value or "").split())


def _journal_text(row) -> str:
    """Return the first meaningful trader-authored note on a row."""
    for field in ("trade_process_notes", "notes"):
        text = _one_line(getattr(row, field, None))
        if text:
            return text
    return ""


def _has_note_text():
    """Narrow obvious empty rows in SQL; ``_journal_text`` remains authoritative."""
    return (
        (Trade.trade_process_notes.isnot(None))
        & (func.trim(Trade.trade_process_notes) != "")
    ) | ((Trade.notes.isnot(None)) & (func.trim(Trade.notes) != ""))


def _hydrate_journal_rows(db, owner: int, wanted: List[int]) -> List[Trade]:
    """Load only the owner's selected journal rows in requested order."""
    if not wanted:
        return []
    rows = db.query(Trade).filter(Trade.user_id == owner, Trade.id.in_(wanted)).all()
    position = {trade_id: index for index, trade_id in enumerate(wanted)}
    rows.sort(key=lambda row: position[row.id])
    return rows


def _admit(
    candidates: List[_Candidate],
) -> Tuple[str, Tuple[PartnerEvidenceSource, ...]]:
    """Atomically admit context lines and their sources under both budgets."""
    blocks: List[str] = []
    sources: List[PartnerEvidenceSource] = []
    emitted_headings: set = set()
    length = 0

    for candidate in candidates:
        if len(sources) >= MAX_EVIDENCE_SOURCES:
            break

        pending: List[str] = []
        if candidate.heading not in emitted_headings:
            pending.append(candidate.heading)
        pending.append(candidate.line)

        added = sum(len(part) for part in pending) + len(pending) - (0 if blocks else 1)
        if length + added > MAX_CONTEXT_CHARS:
            continue

        if candidate.heading not in emitted_headings:
            emitted_headings.add(candidate.heading)
        blocks.extend(pending)
        sources.append(candidate.source)
        length += added

    return "\n".join(blocks), tuple(sources)


def build_global_partner_context(*, user_id: int) -> PartnerContext:
    """Assemble bounded reflective context for one authenticated trader."""
    owner = _require_concrete_user_id(user_id)

    db = SessionLocal()
    try:
        completed_trade_count = db.query(Trade).filter(Trade.user_id == owner).count()

        note_rows = (
            db.query(
                Trade.id,
                Trade.trade_date,
                Trade.trade_process_notes,
                Trade.notes,
            )
            .filter(Trade.user_id == owner, _has_note_text())
            .order_by(Trade.trade_date.desc())
            .all()
        )
        meaningful_ids = [row.id for row in note_rows if _journal_text(row)]
        journal_entry_count = len(meaningful_ids)

        journal_rows = _hydrate_journal_rows(
            db, owner, meaningful_ids[:MAX_JOURNAL_ROWS]
        )
        trade_rows = (
            db.query(Trade)
            .filter(Trade.user_id == owner)
            .order_by(Trade.trade_date.desc())
            .limit(MAX_TRADE_ROWS)
            .all()
        )
    finally:
        db.close()

    strategy_profile = get_active_strategy(owner)
    candidates: List[_Candidate] = []

    for row in journal_rows:
        note = _journal_text(row)
        if not note:
            continue
        trade_date = _one_line(row.trade_date)
        asset = _one_line(row.asset)
        candidates.append(
            _Candidate(
                heading=JOURNAL_HEADING,
                line=f"- {trade_date}: {note}",
                source=PartnerEvidenceSource(
                    kind="journal",
                    record_id=row.id,
                    user_id=owner,
                    label=f"Journal note - {asset} {trade_date}",
                    occurred_on=trade_date,
                ),
            )
        )

    for row in trade_rows:
        trade_date = _one_line(row.trade_date)
        asset = _one_line(row.asset)
        candidates.append(
            _Candidate(
                heading=TRADES_HEADING,
                line=f"- {trade_date} {asset} P&L {_one_line(row.pnl)}",
                source=PartnerEvidenceSource(
                    kind="trade",
                    record_id=row.id,
                    user_id=owner,
                    label=f"{asset} {trade_date}",
                    occurred_on=trade_date,
                ),
            )
        )

    if strategy_profile and strategy_profile.get("id") is not None:
        name = _one_line(strategy_profile.get("name")) or "Strategy Profile"
        candidates.append(
            _Candidate(
                heading=STRATEGY_HEADING,
                line=f"- {name}",
                source=PartnerEvidenceSource(
                    kind="strategy",
                    record_id=int(strategy_profile["id"]),
                    user_id=owner,
                    label=name,
                ),
            )
        )

    context_text, evidence_sources = _admit(candidates)
    return PartnerContext(
        context_text=context_text,
        strategy_profile=strategy_profile,
        evidence_sources=evidence_sources,
        completed_trade_count=completed_trade_count,
        journal_entry_count=journal_entry_count,
    )
