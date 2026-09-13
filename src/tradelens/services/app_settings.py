"""User-scoped persistent application settings."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.exc import IntegrityError

from src.tradelens.db.models import UserSetting
from src.tradelens.db.session import SessionLocal

DEFAULT_TIMEZONE = "America/New_York"
_TIMEZONE_KEY = "trading_timezone"


def _require_concrete_user_id(user_id: int) -> int:
    """Return a settings owner ID or reject ownerless access."""
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("user_id must be a positive integer")
    return user_id


def get_setting(user_id: int, key: str, default=None):
    """Return one user's stored setting, or ``default`` when it is unset."""
    user_id = _require_concrete_user_id(user_id)
    db = SessionLocal()
    try:
        row = (
            db.query(UserSetting)
            .filter(UserSetting.user_id == user_id, UserSetting.key == key)
            .first()
        )
        return row.value if row is not None else default
    finally:
        db.close()


def set_setting(user_id: int, key: str, value) -> None:
    """Create or update one user's setting and refresh its UTC timestamp."""
    user_id = _require_concrete_user_id(user_id)
    now = datetime.now(timezone.utc).isoformat()
    db = SessionLocal()
    try:
        row = (
            db.query(UserSetting)
            .filter(UserSetting.user_id == user_id, UserSetting.key == key)
            .first()
        )
        if row is None:
            row = UserSetting(user_id=user_id, key=key, value=value, updated_at=now)
            db.add(row)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                row = (
                    db.query(UserSetting)
                    .filter(UserSetting.user_id == user_id, UserSetting.key == key)
                    .first()
                )
                if row is None:
                    raise
                row.value = value
                row.updated_at = now
                db.commit()
        else:
            row.value = value
            row.updated_at = now
            db.commit()
    finally:
        db.close()


def get_timezone(user_id: int) -> str:
    """Return one user's saved timezone, with a per-user default."""
    return get_setting(user_id, _TIMEZONE_KEY, DEFAULT_TIMEZONE) or DEFAULT_TIMEZONE


# The six options the Streamlit page offered, kept as a strict allowlist
# (decision S6): no new dependency, and nothing relies on the host's tz
# database. `DEFAULT_TIMEZONE` is the first entry.
TIMEZONE_OPTIONS = (
    "America/New_York",
    "America/Chicago",
    "Europe/London",
    "Asia/Tokyo",
    "Asia/Dubai",
    "UTC",
)


def set_timezone(user_id: int, tz: str) -> None:
    """Persist one user's timezone; a blank value becomes the default.

    Anything outside `TIMEZONE_OPTIONS` is refused before it is stored: every
    date the app derives for this owner — "today", the trading week, New
    Trade's session — is read through this value, and nothing validated it.
    """
    value = tz or DEFAULT_TIMEZONE
    if value not in TIMEZONE_OPTIONS:
        raise ValueError("unsupported_timezone")
    set_setting(user_id, _TIMEZONE_KEY, value)


def today_for_owner(owner: int, *, now_utc: Optional[datetime] = None) -> date:
    """Return the current calendar date in one owner's configured timezone.

    The single source of this rule. Phase 3E's Overview "Today"/"This Week"
    fix (`services/overview._today_for_owner`) and Phase 4's New Trade
    future-date check both resolve the owner's persisted timezone and convert
    a UTC instant through it here, rather than each carrying its own
    zoneinfo logic — two copies of a timezone rule is how they drift. Falls
    back to the product default timezone, and then to UTC, when the owner's
    saved zone is missing or invalid.
    """
    zone_name = get_timezone(owner)
    try:
        zone = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, KeyError, ValueError, OSError):
        try:
            zone = ZoneInfo(DEFAULT_TIMEZONE)
        except (ZoneInfoNotFoundError, KeyError, ValueError, OSError):
            zone = timezone.utc

    instant = now_utc or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(zone).date()
