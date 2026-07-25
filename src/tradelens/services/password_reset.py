"""Password reset by emailed token.

Accounts previously had no contact field, so a forgotten password meant a
lost journal. This is the route back, kept as small as it can be while
still being safe for real accounts.

**Single-use without a token table.** Each token is signed with a key
derived from the account's *current* password hash. Completing a reset
changes that hash, so every token issued against the old one stops
verifying. Nothing to store, nothing to expire-sweep, and a replayed link
simply fails.

**No user enumeration.** `request_reset()` returns the same answer whether
or not the address belongs to an account, so the form cannot be used to
discover who has signed up.

**The token is never returned to the caller.** It goes to the inbox or
nowhere; a UI cannot accidentally render it.

Delivery is plain SMTP from the standard library — no third-party service.
When SMTP is unconfigured, a reset request reports that it could not be
sent rather than silently pretending to have sent one.

Streamlit-free.
"""

from __future__ import annotations

import base64
import hmac
import json
import logging
import os
import secrets as _pysecrets
import smtplib
import time
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Optional

from sqlalchemy.orm import Session

from src.tradelens.db.models import User
from src.tradelens.db.session import SessionLocal
from src.tradelens.services.users import (
    MIN_PASSWORD_LEN,
    hash_password,
    normalise_email,
)

_log = logging.getLogger(__name__)

# Long enough to find the mail, short enough that an old inbox is not a
# standing key to the account.
TOKEN_TTL_S = 30 * 60

# Identical wording for every outcome of a reset request, so the response
# cannot be used to tell whether an address is registered.
_NEUTRAL_MESSAGE = (
    "If that address has a TradeLens account, a reset code is on its way. "
    "The code expires in 30 minutes."
)

_PROCESS_SECRET: Optional[bytes] = None


class EmailNotSent(RuntimeError):
    """Delivery failed, so the user will never receive the reset."""


@dataclass(frozen=True)
class ResetRequest:
    accepted: bool
    message: str


def _read_env(name: str, default: str = "") -> str:
    return os.getenv(name, default) or default


def _base_secret() -> bytes:
    """Signing material shared by every reset token.

    A configured secret keeps tokens valid across restarts. Without one a
    per-process key is generated, so tokens simply stop working after a
    restart — inconvenient, never forgeable.
    """
    global _PROCESS_SECRET
    configured = _read_env("TRADELENS_SESSION_SECRET")
    if configured:
        return configured.encode()
    if _PROCESS_SECRET is None:
        _PROCESS_SECRET = _pysecrets.token_bytes(32)
    return _PROCESS_SECRET


def _signing_key(password_hash: str) -> bytes:
    """Per-account key that changes when the password does.

    This is what makes a token single-use: the hash it was signed against
    no longer exists once the reset completes.
    """
    return _base_secret() + b"|reset|" + password_hash.encode("utf-8")


def _sign(payload: str, password_hash: str) -> str:
    return hmac.new(
        _signing_key(password_hash), payload.encode("utf-8"), "sha256"
    ).hexdigest()


def _load_user(db: Session, user_id: int) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()


def issue_reset_token(user_id: int, now: Optional[float] = None) -> Optional[str]:
    """Return a signed, expiring token for this account, or None if unknown."""
    db: Session = SessionLocal()
    try:
        user = _load_user(db, user_id)
        if user is None:
            return None
        issued_at = time.time() if now is None else now
        payload = json.dumps(
            {"i": user.id, "e": int(issued_at + TOKEN_TTL_S)},
            separators=(",", ":"),
        )
        raw = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")
        return f"{raw}.{_sign(raw, user.password_hash)}"
    finally:
        db.close()


def verify_reset_token(token, now: Optional[float] = None) -> Optional[int]:
    """Return the account id a valid token belongs to, else None."""
    if not token or not isinstance(token, str) or "." not in token:
        return None

    raw, _, signature = token.rpartition(".")
    try:
        payload = json.loads(base64.urlsafe_b64decode(raw.encode("ascii")))
        user_id = int(payload["i"])
        expires_at = int(payload["e"])
    except Exception:  # noqa: BLE001 — any malformed token is simply invalid
        return None

    if expires_at < (time.time() if now is None else now):
        return None

    db: Session = SessionLocal()
    try:
        user = _load_user(db, user_id)
        if user is None:
            return None
        # Signed against the password hash, so this fails once it changes.
        if not hmac.compare_digest(signature, _sign(raw, user.password_hash)):
            return None
        return user.id
    finally:
        db.close()


def complete_reset(token, new_password: str) -> bool:
    """Set a new password using a valid token. Returns whether it applied."""
    if len((new_password or "").strip()) < MIN_PASSWORD_LEN:
        raise ValueError(
            f"Choose a password of at least {MIN_PASSWORD_LEN} characters."
        )

    user_id = verify_reset_token(token)
    if user_id is None:
        return False

    db: Session = SessionLocal()
    try:
        user = _load_user(db, user_id)
        if user is None:
            return False
        user.password_hash = hash_password(new_password)
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# --- delivery --------------------------------------------------------------


def email_configured() -> bool:
    """True when there is somewhere to send from and something to send through."""
    return bool(_read_env("TRADELENS_SMTP_HOST") and _read_env("TRADELENS_SMTP_FROM"))


def send_email(*, to_address: str, subject: str, body: str) -> None:
    """Send one plain-text message over SMTP. Raises EmailNotSent on failure."""
    if not email_configured():
        raise EmailNotSent("SMTP is not configured (TRADELENS_SMTP_HOST/FROM).")

    host = _read_env("TRADELENS_SMTP_HOST")
    port = int(_read_env("TRADELENS_SMTP_PORT", "587") or 587)
    username = _read_env("TRADELENS_SMTP_USER")
    password = _read_env("TRADELENS_SMTP_PASSWORD")
    sender = _read_env("TRADELENS_SMTP_FROM")

    message = EmailMessage()
    message["From"] = sender
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            smtp.ehlo()
            if smtp.has_extn("starttls"):
                smtp.starttls()
                smtp.ehlo()
            if username and password:
                smtp.login(username, password)
            smtp.send_message(message)
    except (smtplib.SMTPException, OSError) as exc:
        raise EmailNotSent(str(exc)) from exc


def _reset_body(token: str) -> str:
    return (
        "Someone asked to reset the password on your TradeLens AI account.\n\n"
        "Paste this code into the reset form to choose a new password.\n\n"
        f"code: {token}\n\n"
        "The code expires in 30 minutes and can only be used once.\n"
        "If this wasn't you, no action is needed — your password has not "
        "changed and nobody can use this code without your inbox.\n"
    )


def request_reset(email) -> ResetRequest:
    """Send a reset code if the address has an account.

    The answer is deliberately the same whether or not it does, so this
    cannot be used to find out who has an account. A genuine delivery
    failure is the one case that reports differently, because a user who
    will never receive the mail must not be told to go and wait for it.
    """
    normalised = normalise_email(email)

    user_id = None
    if normalised is not None:
        db: Session = SessionLocal()
        try:
            user = db.query(User).filter(User.email == normalised).first()
            if user is not None and user.is_active:
                user_id = user.id
        finally:
            db.close()

    if user_id is None:
        return ResetRequest(True, _NEUTRAL_MESSAGE)

    token = issue_reset_token(user_id)
    if token is None:  # pragma: no cover — the row was just read
        return ResetRequest(True, _NEUTRAL_MESSAGE)

    try:
        send_email(
            to_address=normalised,
            subject="Reset your TradeLens AI password",
            body=_reset_body(token),
        )
    except EmailNotSent as exc:
        _log.warning("Password reset email could not be sent: %s", exc)
        return ResetRequest(
            False,
            "We could not send the reset email just now. Please contact "
            "support so we can help you back into your account.",
        )

    return ResetRequest(True, _NEUTRAL_MESSAGE)


__all__ = [
    "EmailNotSent",
    "ResetRequest",
    "TOKEN_TTL_S",
    "complete_reset",
    "email_configured",
    "issue_reset_token",
    "request_reset",
    "send_email",
    "verify_reset_token",
]
