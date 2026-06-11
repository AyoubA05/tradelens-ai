"""
Corrections service — captures field-level diffs between AI-generated and user-saved values.

Append-only: each Save action that changes a value writes one row per changed field.
No Streamlit imports here.
"""
import json
from datetime import datetime, timezone
from typing import Optional

from src.tradelens.db.models import Correction
from src.tradelens.db.session import SessionLocal


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
) -> Optional[Correction]:
    """
    Write a Correction row only when _serialize(ai_value) != _serialize(user_value).
    Returns the saved ORM row if written, or None if values were equal.
    created_at is always set to the current UTC timestamp.
    """
    serialized_ai = _serialize(ai_value)
    serialized_user = _serialize(user_value)

    if serialized_ai == serialized_user:
        return None

    now = datetime.now(timezone.utc).isoformat()
    db = SessionLocal()
    try:
        row = Correction(
            trade_id=trade_id,
            ai_analysis_id=ai_analysis_id,
            field=field,
            ai_value=serialized_ai,
            user_value=serialized_user,
            user_reason=user_reason,
            created_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
    finally:
        db.close()


def get_recent_corrections(limit: int = 10) -> list[dict]:
    """Return the most recent corrections as plain dicts, ordered by id DESC."""
    db = SessionLocal()
    try:
        rows = (
            db.query(Correction)
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
            }
            for r in rows
        ]
    finally:
        db.close()
