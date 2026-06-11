"""
Strategy Profile service.

Single-user MVP: exactly one active profile at a time (is_active = 1).
Returns plain dicts so AI services (vision, journal, grading) remain ORM-free.
No Streamlit imports here.
"""
from datetime import datetime, timezone
from typing import Optional

from src.tradelens.db.models import Strategy
from src.tradelens.db.session import SessionLocal

_PROFILE_FIELDS = {
    "name",
    "trading_style",
    "markets",
    "timeframes",
    "entry_rules",
    "stop_rules",
    "take_profit_rules",
    "risk_rules",
    "setups_traded",
    "setups_avoided",
    "news_session_rules",
    "common_mistakes",
}


def _to_dict(row: Strategy) -> dict:
    return {field: getattr(row, field, None) for field in _PROFILE_FIELDS | {"id", "is_active", "created_at", "updated_at"}}


def get_active_strategy() -> Optional[dict]:
    """
    Return the active Strategy profile as a plain dict, or None if none exists.
    Queries WHERE is_active = 1.
    """
    db = SessionLocal()
    try:
        row = db.query(Strategy).filter(Strategy.is_active == 1).first()
        return _to_dict(row) if row else None
    finally:
        db.close()


def upsert_strategy_profile(**fields) -> dict:
    """
    Create or update the single active strategy profile.

    Semantics:
    - Deactivate all existing rows (is_active = 0) first to enforce single-active.
    - If an active row already exists, update it in-place.
    - If no rows exist at all, create a new one.
    - Always sets is_active = 1, refreshes updated_at, sets created_at on first create.
    - Returns the saved profile as a dict.
    """
    now = datetime.now(timezone.utc).isoformat()
    db = SessionLocal()
    try:
        # Enforce single active: deactivate all first
        db.query(Strategy).update({"is_active": 0})

        row = db.query(Strategy).first()
        if row is None:
            row = Strategy(is_active=1, created_at=now, updated_at=now)
            db.add(row)
        else:
            row.is_active = 1
            row.updated_at = now
            if row.created_at is None:
                row.created_at = now

        for key, val in fields.items():
            if key in _PROFILE_FIELDS:
                setattr(row, key, val)

        db.commit()
        db.refresh(row)
        return _to_dict(row)
    finally:
        db.close()
