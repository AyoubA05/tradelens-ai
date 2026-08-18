"""Revocable server-side sessions for the Streamlit app.

Replaces the self-contained HMAC token that used to ride in ``?auth=``. That
token could not be revoked: signing out cleared ``st.session_state`` and popped
the URL parameter, but the token itself stayed cryptographically valid for its
full 24 hours, so anyone holding a copied link could sign straight back in.
Revocation here is a row update, which is what makes sign-out mean something.

What a session credential is:

* 32 random bytes — 256 bits, opaque, carrying no username, id, email, or
  expiry. It is a lookup key and nothing else.
* stored only as ``sha256(token)``, so a database read yields nothing usable.
* bounded by **two independent clocks**, both enforced server-side:
  ``last_seen_at`` slides an 8-hour idle window, while ``expires_at`` is written
  once at creation and updated by nothing. Activity can extend the idle bound
  and can never extend the absolute one, so a continuously active session still
  ends at 12 hours.

**Known limitation, deliberately not hidden.** For the beta the credential is
carried in the Streamlit URL, because Streamlit Community Cloud offers no
server-side cookie write outside its own OIDC flow. Anyone holding the URL is
signed in until the session expires or is revoked. That is strictly better than
what it replaces — revocable, claimless, and a third of the lifetime — but it is
**not** equivalent to an HttpOnly cookie and must never be described as one. The
fix is Streamlit's native OIDC, scoped as its own project.

No Streamlit import.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import DateTime, Integer, text

from src.tradelens.db.session import SessionLocal

# Raw text() queries bypass SQLAlchemy's result coercion, so a TIMESTAMPTZ comes
# back as a datetime on PostgreSQL but as a bare string on SQLite. Declaring the
# column types makes both backends return datetimes, which is what the timeout
# comparisons need — and is safer than parsing strings, since it keeps one code
# path rather than one per dialect.
_SESSION_ROW_TYPES = {
    "user_id": Integer(),
    "expires_at": DateTime(timezone=True),
    "last_seen_at": DateTime(timezone=True),
    "revoked_at": DateTime(timezone=True),
}

IDLE_TIMEOUT_S = 8 * 3600
ABSOLUTE_TIMEOUT_S = 12 * 3600

_SWEEP_AFTER_DAYS = 30


# Credential domains. A session token is hashed with its surface's prefix
# before storage or lookup, so a token minted for one surface simply does not
# hash to anything the other surface can find.
#
# This is the control that cannot be forgotten: there is no WHERE clause to
# omit, because the hash function each surface uses IS the domain. The
# `surface` column is the second, auditable control alongside it.
#
# Versioned so a future rotation stays unambiguous. UTF-8 throughout.
WEBSITE_DOMAIN = "tl.website.v1|"
STREAMLIT_DOMAIN = "tl.streamlit.v1|"

SURFACE_WEBSITE = "website"
SURFACE_STREAMLIT = "streamlit"


def _hash(token: str, domain: str) -> str:
    """SHA-256 hex of ``domain + token``, UTF-8 encoded.

    The domain is mandatory. An undomained ``sha256(token)`` is no longer a
    valid session hash anywhere, and no fallback to it exists — a lookup that
    tried both would reintroduce exactly the cross-surface ambiguity this
    replaces.
    """
    return hashlib.sha256((domain + token).encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value):
    """Normalise a timestamp read back from the database.

    PostgreSQL returns aware datetimes for TIMESTAMPTZ; SQLite, used by the test
    suite, drops the zone and returns naive ones. Comparing the two raises, so
    every value is coerced to UTC-aware before any comparison.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def open_streamlit_session(user_id: int, now: Optional[datetime] = None) -> str:
    """Mint a session credential. Returns the raw token; stores only its hash.

    ``expires_at`` is written here and by nothing else. That single fact is what
    makes the 12-hour cap absolute rather than merely nominal.
    """
    if user_id is None:
        raise ValueError("a session requires a concrete user id")

    started = now or _now()
    token = secrets.token_urlsafe(32)
    db = SessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO auth_sessions "
                "(token_hash, user_id, created_at, expires_at, last_seen_at, surface) "
                "VALUES (:h, :u, :c, :e, :l, :s)"
            ),
            {
                "h": _hash(token, STREAMLIT_DOMAIN),
                "s": SURFACE_STREAMLIT,
                "u": user_id,
                "c": started,
                "e": started + timedelta(seconds=ABSOLUTE_TIMEOUT_S),
                "l": started,
            },
        )
        db.execute(
            text(
                "DELETE FROM auth_sessions WHERE expires_at < :cutoff "
                "AND revoked_at IS NULL"
            ),
            {"cutoff": started - timedelta(days=_SWEEP_AFTER_DAYS)},
        )
        db.commit()
        return token
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def restore_streamlit_session(token, now: Optional[datetime] = None) -> Optional[int]:
    """Resolve a credential to a user id, sliding the idle window.

    Returns None — failing closed — when the session is unknown, revoked, past
    its absolute expiry, or idle beyond the timeout. All four look identical to
    the caller.
    """
    if not token or not isinstance(token, str):
        return None

    at = now or _now()
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT user_id, expires_at, last_seen_at, revoked_at "
                "FROM auth_sessions WHERE token_hash = :h AND surface = :s"
            ).columns(**_SESSION_ROW_TYPES),
            {"h": _hash(token, STREAMLIT_DOMAIN), "s": SURFACE_STREAMLIT},
        ).first()
        if row is None:
            return None

        user_id, expires_at, last_seen_at, revoked_at = row
        if revoked_at is not None:
            return None
        if _as_aware(expires_at) <= at:
            return None
        if at - _as_aware(last_seen_at) > timedelta(seconds=IDLE_TIMEOUT_S):
            return None

        # Slide the idle window only. expires_at is never touched here.
        db.execute(
            text(
                "UPDATE auth_sessions SET last_seen_at = :now "
                "WHERE token_hash = :h AND surface = :s"
            ),
            {"now": at, "h": _hash(token, STREAMLIT_DOMAIN), "s": SURFACE_STREAMLIT},
        )
        db.commit()
        return int(user_id)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def revoke_streamlit_session(token, now: Optional[datetime] = None) -> bool:
    """Revoke a session. Returns whether a live session was actually ended.

    This is what sign-out calls. Popping the URL parameter without this is the
    defect that let a copied link keep working after logout.
    """
    if not token or not isinstance(token, str):
        return False

    at = now or _now()
    db = SessionLocal()
    try:
        result = db.execute(
            text(
                "UPDATE auth_sessions SET revoked_at = :now "
                "WHERE token_hash = :h AND surface = :s AND revoked_at IS NULL"
            ),
            {"now": at, "h": _hash(token, STREAMLIT_DOMAIN), "s": SURFACE_STREAMLIT},
        )
        db.commit()
        return result.rowcount == 1
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def revoke_all_for_user(user_id: int, now: Optional[datetime] = None) -> int:
    """Revoke every live session for an account. Returns how many ended.

    Needed by password reset: changing a password must not leave sessions opened
    with the old one still valid, which is the whole point of resetting it.
    """
    at = now or _now()
    db = SessionLocal()
    try:
        result = db.execute(
            text(
                "UPDATE auth_sessions SET revoked_at = :now "
                "WHERE user_id = :u AND revoked_at IS NULL"
            ),
            {"now": at, "u": user_id},
        )
        db.commit()
        return int(result.rowcount)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def restore_website_session(token, now: Optional[datetime] = None) -> Optional[int]:
    """Resolve a WEBSITE session credential to a user id, sliding the idle window.

    The Python counterpart of ``authenticateWebsiteRequest`` in
    ``web/lib/auth/session.ts``, and deliberately a re-check rather than a
    convenience: the API backend must not act on an account merely because the
    Next.js layer said it had already validated the session. A bug or a
    compromise there would otherwise be sufficient on its own.

    All five conditions, matching the TypeScript exactly:

        hash matches a row with surface='website'
        revoked_at IS NULL
        expires_at > now
        now - last_seen_at < 8h
        users.is_active = 1

    Returns None — failing closed — when any of them does not hold. All five
    failures look identical to the caller.

    ``is_active`` is joined here even though ``restore_streamlit_session`` does
    not check it. That is not an inconsistency to tidy away: this function
    mirrors the website contract, where a disabled account must not be able to
    act through a credential minted while it was still enabled.

    ``expires_at`` is never touched, which is what keeps the 12-hour cap
    absolute rather than something activity can push indefinitely.
    """
    if not token or not isinstance(token, str):
        return None

    at = now or _now()
    digest = _hash(token, WEBSITE_DOMAIN)
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT s.user_id, s.expires_at, s.last_seen_at, s.revoked_at "
                "FROM auth_sessions s JOIN users u ON u.id = s.user_id "
                "WHERE s.token_hash = :h AND s.surface = :s AND u.is_active = 1"
            ).columns(**_SESSION_ROW_TYPES),
            {"h": digest, "s": SURFACE_WEBSITE},
        ).first()
        if row is None:
            return None

        user_id, expires_at, last_seen_at, revoked_at = row
        if revoked_at is not None:
            return None
        if _as_aware(expires_at) <= at:
            return None
        if at - _as_aware(last_seen_at) > timedelta(seconds=IDLE_TIMEOUT_S):
            return None

        db.execute(
            text(
                "UPDATE auth_sessions SET last_seen_at = :now "
                "WHERE token_hash = :h AND surface = :s"
            ),
            {"now": at, "h": digest, "s": SURFACE_WEBSITE},
        )
        db.commit()
        return int(user_id)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
