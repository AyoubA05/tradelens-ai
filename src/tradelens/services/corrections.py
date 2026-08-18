"""
Corrections service — captures field-level diffs between AI-generated and user-saved values.

Append-only: each Save action that changes a value writes one row per changed field.
No Streamlit imports here.
"""

import json
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Optional

from src.tradelens.db.models import AIAnalysis, Correction, Trade
from src.tradelens.db.session import SessionLocal
from src.tradelens.services.ownership import require_user_id

# The owner of the current request. `ai_client`'s few-shot injection has no user
# argument, so this is how it learns whose corrections it may read.
#
# The default is a sentinel that RESOLVES TO A REFUSAL, not to the legacy NULL
# tenant. Under Streamlit an unset value meant "the single legacy user" and was
# harmless; under a server it would mean "whatever the last request left here",
# and a wrong answer is worse than an error.
_UNSCOPED = object()
_ACTIVE_USER: ContextVar[object] = ContextVar(
    "tradelens_corrections_user", default=_UNSCOPED
)
_UNSET = object()  # "argument not passed", distinct from an explicit value


def _resolve_user(user_id) -> int:
    if user_id is not _UNSET:
        return require_user_id(user_id)
    active = _ACTIVE_USER.get()
    if active is _UNSCOPED:
        raise LookupError(
            "no correction scope is active; call corrections_scope(user_id) "
            "or pass user_id explicitly"
        )
    return require_user_id(active)


@contextmanager
def corrections_scope(user_id: int):
    """Scope correction reads and writes to one user for the duration of a block.

    Reset happens through the token in a `finally`, never a bare `.set()`.
    FastAPI runs sync handlers in a threadpool where a worker thread is reused,
    so a value left behind is a value the next request can observe.
    """
    token = _ACTIVE_USER.set(require_user_id(user_id))
    try:
        yield
    finally:
        _ACTIVE_USER.reset(token)


def set_corrections_user(user_id: int) -> None:
    """Scope subsequent correction reads/writes. Prefer `corrections_scope`.

    Retained for the Streamlit page path, which has no block to wrap: a
    Streamlit script run is the scope. Deleted with `ui/` at Phase 10.
    """
    _ACTIVE_USER.set(require_user_id(user_id))


def _serialize(value) -> Optional[str]:
    """
    Normalize a value to a comparable string.

    - None / empty string → None (treated as equivalent)
    - list / dict → json.dumps with sort_keys=True for stable equality
    - everything else → str()
    """
    if value is None or value == "":
        return None
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def record_correction(
    trade_id: int,
    ai_analysis_id: int,
    field: str,
    ai_value,
    user_value,
    user_reason: Optional[str] = None,
    user_id=_UNSET,
) -> Optional[Correction]:
    """
    Write a Correction row only when _serialize(ai_value) != _serialize(user_value).
    Returns the saved ORM row if written, or None if values were equal.
    created_at is always set to the current UTC timestamp.
    Owned by `user_id` (defaults to the active user set by the auth layer).
    """
    serialized_ai = _serialize(ai_value)
    serialized_user = _serialize(user_value)

    if serialized_ai == serialized_user:
        return None

    owner = _resolve_user(user_id)
    now = datetime.now(timezone.utc).isoformat()
    db = SessionLocal()
    try:
        owned_context = (
            db.query(AIAnalysis.id)
            .join(Trade, Trade.id == AIAnalysis.trade_id)
            .filter(
                AIAnalysis.id == ai_analysis_id,
                AIAnalysis.trade_id == trade_id,
                Trade.user_id == owner,
            )
            .first()
        )
        if owned_context is None:
            raise ValueError("correction context not found")
        row = Correction(
            trade_id=trade_id,
            ai_analysis_id=ai_analysis_id,
            field=field,
            ai_value=serialized_ai,
            user_value=serialized_user,
            user_reason=user_reason,
            created_at=now,
            user_id=owner,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
    finally:
        db.close()


_FEWSHOT_TOKEN_BUDGET = 800  # keep the injected <past_corrections> block small


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token). Good enough for budgeting a block."""
    return (len(text) + 3) // 4


def build_correction_few_shot(
    limit: int = 10, scope: Optional[str] = None, user_id=_UNSET
) -> str:
    """
    Build a token-budgeted ``<past_corrections>`` block from recent corrections.

    The trader's overrides of the AI are surfaced so every downstream AI call can
    avoid repeating mistakes the trader already corrected. Entries are de-duplicated
    by (field, corrected value) and ranked most-repeated first, then most-recent;
    a repeat count is shown so the model weights persistent corrections higher.

    Args:
        limit: max number of distinct corrections to include (<=0 → "").
        scope: optional field name to restrict the block to a single field.

    Returns:
        A self-contained ``<past_corrections>…</past_corrections>`` string, kept
        under ~800 tokens, or "" when there is nothing to show. Never None.
    """
    if limit <= 0:
        return ""

    pool = get_recent_corrections(limit=max(limit * 5, 50), user_id=user_id)
    if scope:
        pool = [c for c in pool if c.get("field") == scope]
    if not pool:
        return ""

    # De-dupe by (field, corrected value); track count and recency (lower idx = newer).
    groups: dict = {}
    for idx, c in enumerate(pool):
        key = (c.get("field"), c.get("user_value"))
        g = groups.get(key)
        if g is None:
            groups[key] = {
                "field": c.get("field"),
                "user_value": c.get("user_value"),
                "ai_value": c.get("ai_value"),
                "user_reason": c.get("user_reason"),
                "count": 1,
                "idx": idx,
            }
        else:
            g["count"] += 1

    ordered = sorted(groups.values(), key=lambda g: (-g["count"], g["idx"]))

    header = "<past_corrections>"
    footer = "</past_corrections>"
    used = _estimate_tokens(header) + _estimate_tokens(footer)
    lines: list = []
    for g in ordered[:limit]:
        line = f"- {g['field']}: prefer {g['user_value']!r} over {g['ai_value']!r}"
        if g["count"] > 1:
            line += f" (corrected {g['count']}x)"
        if g["user_reason"]:
            line += f" — {g['user_reason']}"
        cost = _estimate_tokens(line) + 1  # +1 for the joining newline
        if used + cost > _FEWSHOT_TOKEN_BUDGET:
            break
        lines.append(line)
        used += cost

    if not lines:
        return ""
    return "\n".join([header, *lines, footer])


def count_corrections(user_id=_UNSET) -> int:
    """The user's total recorded corrections (for the 'learned N' badge)."""
    db = SessionLocal()
    try:
        return (
            db.query(Correction)
            .filter(Correction.user_id == _resolve_user(user_id))
            .count()
        )
    finally:
        db.close()


def repeated_corrections(threshold: int = 5, user_id=_UNSET) -> list[dict]:
    """
    Return corrections the trader has made at least `threshold` times.

    Grouped by (field, corrected value). Powers the repeat-threshold toast that
    suggests promoting a persistent correction into the Strategy Profile.

    Returns a list of {field, user_value, ai_value, count} dicts, count desc.
    """
    db = SessionLocal()
    try:
        rows = (
            db.query(Correction)
            .filter(Correction.user_id == _resolve_user(user_id))
            .all()
        )
    finally:
        db.close()

    groups: dict = {}
    for r in rows:
        key = (r.field, r.user_value)
        g = groups.get(key)
        if g is None:
            groups[key] = {
                "field": r.field,
                "user_value": r.user_value,
                "ai_value": r.ai_value,
                "count": 1,
            }
        else:
            g["count"] += 1

    result = [g for g in groups.values() if g["count"] >= threshold]
    result.sort(key=lambda g: g["count"], reverse=True)
    return result


def get_recent_corrections(limit: int = 10, user_id=_UNSET) -> list[dict]:
    """The user's most recent corrections as plain dicts, ordered by id DESC."""
    db = SessionLocal()
    try:
        rows = (
            db.query(Correction)
            .filter(Correction.user_id == _resolve_user(user_id))
            .order_by(Correction.id.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": r.id,
                "trade_id": r.trade_id,
                "ai_analysis_id": r.ai_analysis_id,
                "field": r.field,
                "ai_value": r.ai_value,
                "user_value": r.user_value,
                "user_reason": r.user_reason,
                "created_at": r.created_at,
                "user_id": r.user_id,
            }
            for r in rows
        ]
    finally:
        db.close()
