"""User-scoped persistent application settings."""

from __future__ import annotations

from datetime import datetime, timezone

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


def set_timezone(user_id: int, tz: str) -> None:
    """Persist one user's timezone; a blank value becomes the default."""
    set_setting(user_id, _TIMEZONE_KEY, tz or DEFAULT_TIMEZONE)
