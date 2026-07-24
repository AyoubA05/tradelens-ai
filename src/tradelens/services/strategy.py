"""
Strategy Profile service.

Single-user MVP: exactly one active profile at a time (is_active = 1).
Returns plain dicts so AI services (vision, journal, grading) remain ORM-free.
No Streamlit imports here.
"""

import re
from datetime import datetime, timezone
from typing import Optional

from src.tradelens.db.models import Strategy
from src.tradelens.db.session import SessionLocal

# Split on commas / semicolons / newlines / standalone "and" — NOT on "+", "&",
# or "/" so multi-token items survive ("BOS + OB Retest", "S/R Bounce").
_LIST_SPLIT_RE = re.compile(r"\s*(?:,|;|\n|\band\b)\s*", re.IGNORECASE)
_TF_TOKEN_RE = re.compile(r"\d+\s*(?:m|min|h|hr|d)\b", re.IGNORECASE)

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


# ---------------------------------------------------------------------------
# Parsing helpers (Session E) — turn free-text profile fields into option lists
# so the New Trade form can offer profile-derived defaults. Pure + testable.
# ---------------------------------------------------------------------------


def parse_list(text) -> list:
    """Split a free-text field into clean items.

    Robust to commas, ';', newlines, 'and', extra whitespace, and trailing
    punctuation; de-duplicates case-insensitively while preserving order and the
    original casing. Multi-token items ("BOS + OB Retest", "S/R Bounce") survive.
    """
    if not text:
        return []
    seen, out = set(), []
    for part in _LIST_SPLIT_RE.split(str(text)):
        item = part.strip().strip(".").strip()
        key = item.lower()
        if item and key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _normalize_tf(token: str) -> str:
    """Normalize a timeframe token to the app's set (1m/5m/15m/1H/4H/D)."""
    t = token.strip().lower().replace(" ", "")
    t = t.replace("min", "m").replace("hr", "h")
    if t.endswith("h"):
        return t[:-1] + "H"
    if t.endswith("d"):
        return "D"
    return t


def parse_markets(profile: Optional[dict]) -> list:
    """Asset symbols from a profile's markets field, uppercased.

    'NQ, MNQ and NG' -> ['NQ', 'MNQ', 'NG'].
    """
    return [item.upper() for item in parse_list((profile or {}).get("markets"))]


def parse_timeframes(profile: Optional[dict]) -> dict:
    """Extract {'entry': '1m', 'htf': '15m'} from a profile's timeframes field.

    Honors explicit 'Xm entry' / 'Xm HTF' wording; otherwise falls back to the
    first token as entry and the last as HTF.
    """
    text = (profile or {}).get("timeframes") or ""
    low = text.lower()
    entry = htf = None
    em = re.search(r"(\d+\s*(?:m|min|h|hr|d))\s*(?:entry|ltf)", low)
    hm = re.search(r"(\d+\s*(?:m|min|h|hr|d))\s*(?:htf|higher)", low)
    if em:
        entry = _normalize_tf(em.group(1))
    if hm:
        htf = _normalize_tf(hm.group(1))
    tokens = [_normalize_tf(t) for t in _TF_TOKEN_RE.findall(text)]
    if entry is None and tokens:
        entry = tokens[0]
    if htf is None and len(tokens) > 1:
        htf = tokens[-1]
    return {"entry": entry, "htf": htf}


def parse_setups(profile: Optional[dict]) -> list:
    """Setup options parsed from a profile's setups_traded field."""
    return parse_list((profile or {}).get("setups_traded"))


def parse_mistakes(profile: Optional[dict]) -> list:
    """Common-mistake tag options parsed from a profile's common_mistakes field."""
    return parse_list((profile or {}).get("common_mistakes"))


def _to_dict(row: Strategy) -> dict:
    return {
        field: getattr(row, field, None)
        for field in _PROFILE_FIELDS | {"id", "is_active", "created_at", "updated_at"}
    }


def _require_concrete_user_id(user_id: int) -> int:
    """Return a concrete strategy owner ID or reject ownerless access."""
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("user_id must be a positive integer")
    return user_id


def get_active_strategy(user_id: int) -> Optional[dict]:
    """
    Return a user's active Strategy profile as a plain dict, or None if none exists.
    """
    user_id = _require_concrete_user_id(user_id)
    db = SessionLocal()
    try:
        row = (
            db.query(Strategy)
            .filter(Strategy.user_id == user_id, Strategy.is_active == 1)
            .first()
        )
        return _to_dict(row) if row else None
    finally:
        db.close()


def upsert_strategy_profile(user_id: int, **fields) -> dict:
    """
    Create or update a user's single active strategy profile.

    Semantics:
    - Deactivate this user's existing rows (is_active = 0) first.
    - If this user already has a row, update it in-place.
    - If this user has no rows, create a new one.
    - Always sets is_active = 1, refreshes updated_at, sets created_at on first create.
    - Returns the saved profile as a dict.
    """
    user_id = _require_concrete_user_id(user_id)
    now = datetime.now(timezone.utc).isoformat()
    db = SessionLocal()
    try:
        # Enforce one active profile for this user only.
        db.query(Strategy).filter(Strategy.user_id == user_id).update({"is_active": 0})

        row = db.query(Strategy).filter(Strategy.user_id == user_id).first()
        if row is None:
            row = Strategy(user_id=user_id, is_active=1, created_at=now, updated_at=now)
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


def append_insight(user_id: int, insight: str, field: str = "risk_rules") -> dict:
    """
    Append a pattern's suggested rule to a Text field of the user's active profile.

    Powers the Analytics "Add to Strategy Profile" button. Creates an active
    profile if none exists. Existing content is preserved — the insight is added
    as its own bullet line. Blank insights are a no-op. Returns the saved profile.

    Raises ValueError if `field` is not a writable profile field.
    """
    user_id = _require_concrete_user_id(user_id)
    if field not in _PROFILE_FIELDS:
        raise ValueError(f"Unknown strategy field: {field}")

    text = (insight or "").strip()
    now = datetime.now(timezone.utc).isoformat()
    db = SessionLocal()
    try:
        row = (
            db.query(Strategy)
            .filter(Strategy.user_id == user_id, Strategy.is_active == 1)
            .first()
        )
        if row is None:
            row = Strategy(
                user_id=user_id,
                name="My Strategy",
                is_active=1,
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            db.flush()

        if text:
            existing = (getattr(row, field, None) or "").strip()
            bullet = f"• {text}"
            setattr(row, field, f"{existing}\n{bullet}".strip() if existing else bullet)
            row.updated_at = now

        db.commit()
        db.refresh(row)
        return _to_dict(row)
    finally:
        db.close()
