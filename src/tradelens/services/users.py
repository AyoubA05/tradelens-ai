"""
User accounts service (Session B — multi-user auth).

Pure DB + bcrypt; no Streamlit. Login orchestration (DB-vs-secrets fallback)
and the invite-code check live in the UI layer (ui/components/auth.py); this
module only owns the users table and password hashing/verification.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

import bcrypt

from src.tradelens.db.models import User
from src.tradelens.db.session import SessionLocal

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,20}$")
MIN_PASSWORD_LEN = 8


def is_valid_username(username: str) -> bool:
    """3–20 chars, alphanumeric + underscore only."""
    return bool(_USERNAME_RE.match(username or ""))


def users_exist() -> bool:
    """True once at least one DB user has been created."""
    db = SessionLocal()
    try:
        return db.query(User).count() > 0
    finally:
        db.close()


def get_user(username: str) -> Optional[User]:
    db = SessionLocal()
    try:
        return db.query(User).filter(User.username == username).first()
    finally:
        db.close()


def username_taken(username: str) -> bool:
    return get_user(username) is not None


def hash_password(password: str) -> str:
    """bcrypt hash, stored as a UTF-8 string."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_user(username: str, password: str) -> User:
    """Insert a new user with a bcrypt-hashed password. Returns the saved User.

    Caller is responsible for validation (username format, password length,
    uniqueness, invite code) — this performs the insert only.
    """
    now = datetime.now(timezone.utc).isoformat()
    db = SessionLocal()
    try:
        user = User(
            username=username,
            password_hash=hash_password(password),
            is_active=1,
            created_at=now,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def authenticate(username: str, password: str) -> Optional[User]:
    """Return the active User when the bcrypt password matches, else None."""
    user = get_user(username)
    if user is None or not user.is_active:
        return None
    try:
        if bcrypt.checkpw(password.encode("utf-8"), user.password_hash.encode("utf-8")):
            return user
    except (ValueError, TypeError):
        return None
    return None
