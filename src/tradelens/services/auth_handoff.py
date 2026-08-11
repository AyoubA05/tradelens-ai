"""One-time credential handing a signed-in user from the site into Streamlit.

The site authenticates on tradelensai.io; the journal runs on a different origin
under Streamlit. Something has to cross that boundary, and the thing that
crosses must not itself be a durable session — see ``auth_sessions`` for what
the user actually ends up holding.

Design constraints, all enforced here rather than by convention:

* **Opaque.** 32 random bytes. It encodes no user id, email, or expiry — it is a
  lookup key, worthless without the row it points at.
* **Hashed at rest.** Only ``sha256(token)`` is stored, so a database read
  yields nothing replayable.
* **120 seconds.** Long enough for a redirect, short enough that a leaked URL in
  a proxy log or browser history is almost certainly already dead.
* **One-time, atomically.** Redemption is a conditional UPDATE, never a
  read-then-write. Streamlit reruns scripts concurrently and a user can open two
  tabs on the same redirect URL; without the compare-and-swap both would win.

No Streamlit import: this is a service, and it is unit-testable without a
browser session.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text

from src.tradelens.db.session import SessionLocal

# Deliberately short. The token exists only to survive one HTTP redirect.
HANDOFF_TTL_S = 120

# Retention for consumed/expired rows. Swept opportunistically on issue so no
# scheduled job is needed; 30 days keeps a forensic trail of redemptions.
_SWEEP_AFTER_DAYS = 30


def _hash(token: str) -> str:
    """SHA-256 hex digest. The only form of the token that reaches storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def issue_handoff(user_id: int, now: Optional[datetime] = None) -> str:
    """Mint a one-time handoff credential for this account.

    Returns the raw token, which is the only time it exists in plaintext. The
    caller puts it in the redirect URL; nothing persists it.
    """
    if user_id is None:
        raise ValueError("handoff requires a concrete user id")

    issued = now or _now()
    token = secrets.token_urlsafe(32)
    db = SessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO auth_handoffs (token_hash, user_id, created_at, expires_at) "
                "VALUES (:h, :u, :c, :e)"
            ),
            {
                "h": _hash(token),
                "u": user_id,
                "c": issued,
                "e": issued + timedelta(seconds=HANDOFF_TTL_S),
            },
        )
        db.execute(
            text("DELETE FROM auth_handoffs WHERE created_at < :cutoff"),
            {"cutoff": issued - timedelta(days=_SWEEP_AFTER_DAYS)},
        )
        db.commit()
        return token
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def redeem_handoff(token, now: Optional[datetime] = None) -> Optional[int]:
    """Consume a handoff credential exactly once. Returns the user id, or None.

    The decision is made by a single conditional UPDATE. Reading the row first
    and then marking it consumed would let two concurrent redemptions both
    observe an unconsumed row and both proceed — which, given Streamlit reruns
    and duplicate tabs, is a routine occurrence rather than a rare race.

    ``rowcount == 1`` is the winner. Everyone else gets None: expired, already
    consumed, and unknown all fail the same way, so a caller cannot distinguish
    them and neither can an attacker.
    """
    if not token or not isinstance(token, str):
        return None

    at = now or _now()
    db = SessionLocal()
    try:
        token_hash = _hash(token)

        # Candidate user id. Not trusted on its own — the UPDATE below decides.
        row = db.execute(
            text("SELECT user_id FROM auth_handoffs WHERE token_hash = :h"),
            {"h": token_hash},
        ).first()
        if row is None:
            return None

        result = db.execute(
            text(
                "UPDATE auth_handoffs SET consumed_at = :now "
                "WHERE token_hash = :h AND consumed_at IS NULL AND expires_at > :now"
            ),
            {"h": token_hash, "now": at},
        )
        db.commit()
        if result.rowcount != 1:
            return None
        return int(row[0])
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
