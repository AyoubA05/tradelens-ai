"""Atomic exchange of a one-time handoff for a durable Streamlit session.

This is the seam where the website hands a user to the app, and the one place
where getting the transaction boundary wrong has a user-visible cost that cannot
be retried.

**Why one transaction and not two.** The obvious implementation is
``redeem_handoff()`` then ``open_streamlit_session()`` — two calls, two commits.
Between those commits there is a window where the handoff is permanently burned
and no session exists. A user hitting that window sees "this sign-in link is no
longer valid" for a link that *was* valid, and cannot recover: the token is
single-use, so retrying fails too. They would have to go back to the website and
start again, with no explanation. Both statements therefore share one
transaction and commit together or not at all.

**Three credentials, still distinct.** The handoff is hashed with its own
scheme, the new session with ``tl.streamlit.v1|``, and the website cookie with
``tl.website.v1|``. Nothing here reads or writes a website credential, and the
handoff never becomes the session — a fresh 256-bit value is generated.

Streamlit-free: this is a service and is unit-testable without a browser.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text

from src.tradelens.db.session import SessionLocal
from src.tradelens.services.auth_sessions import (
    ABSOLUTE_TIMEOUT_S,
    STREAMLIT_DOMAIN,
    SURFACE_STREAMLIT,
)


def _handoff_hash(token: str) -> str:
    """The canonical handoff hash, matching services/auth_handoff.py exactly.

    Deliberately *not* domain-prefixed: handoffs are their own credential
    domain, stored in their own table, and changing their scheme because the
    session scheme changed would break the issuer for no benefit.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _session_hash(token: str) -> str:
    return hashlib.sha256((STREAMLIT_DOMAIN + token).encode("utf-8")).hexdigest()


def _new_session_token() -> str:
    """256 bits, opaque. Separated so a test can force a collision."""
    return secrets.token_urlsafe(32)


def exchange_handoff_for_streamlit_session(
    raw_ht, now: Optional[datetime] = None
) -> Optional[str]:
    """Consume a handoff and mint a Streamlit session, atomically.

    Returns the raw Streamlit session token, or ``None`` when the handoff is
    malformed, unknown, expired, already consumed, or belongs to an account that
    is no longer eligible. Every one of those looks identical to the caller, so
    a failed link cannot be used to probe which tokens once existed.

    Eligibility is re-checked here rather than trusted from issuance: a handoff
    lives 120 seconds, and an account can be deactivated, have its verification
    revoked, or be reset inside that window.
    """
    if not raw_ht or not isinstance(raw_ht, str):
        return None

    at = now or datetime.now(timezone.utc)
    session_token = _new_session_token()

    db = SessionLocal()
    try:
        # Claim the handoff with a single conditional UPDATE joined to users, so
        # the eligibility re-check and the claim are one indivisible decision.
        # A read-then-write would let two concurrent exchanges both see an
        # unconsumed row — routine here, since a user can refresh or open a
        # second tab on the same redirect.
        token_hash = _handoff_hash(raw_ht)

        # Candidate lookup. Not trusted on its own — the conditional UPDATE
        # below is what actually decides. A correlated subquery rather than an
        # UPDATE..FROM join, because SQLite (the test suite) does not support
        # the aliased-FROM form that PostgreSQL does, and one statement that
        # runs identically on both is worth more than two dialect variants.
        #
        # The boolean comparisons use `true`, not `1`. PostgreSQL has a real
        # BOOLEAN type and rejects `= 1` outright; SQLite stores booleans as
        # integers but accepts the `true` keyword, so this form works on both.
        # The integer `is_active` column stays `= 1` because it genuinely is an
        # integer on both backends.
        candidate = db.execute(
            text("SELECT user_id FROM auth_handoffs WHERE token_hash = :h"),
            {"h": token_hash},
        ).first()
        if candidate is None:
            db.rollback()
            return None

        claimed = db.execute(
            text(
                """
                UPDATE auth_handoffs
                   SET consumed_at = :now
                 WHERE token_hash = :h
                   AND consumed_at IS NULL
                   AND expires_at > :now
                   AND user_id IN (
                       SELECT id FROM users
                        WHERE is_active = 1
                          AND onboarding_completed = true
                          AND NOT (email_verification_required = true
                                   AND email_verified_at IS NULL)
                   )
                """
            ),
            {"h": token_hash, "now": at},
        )

        # rowcount == 1 is the sole winner. Two concurrent exchanges both see an
        # unconsumed candidate; only one can satisfy consumed_at IS NULL here.
        if claimed.rowcount != 1:
            db.rollback()
            return None

        user_id = int(candidate[0])

        # Same transaction. If this raises — a unique violation, a constraint
        # failure, a lost connection — the rollback below undoes the consume and
        # the handoff stays redeemable.
        db.execute(
            text(
                "INSERT INTO auth_sessions "
                "(token_hash, user_id, created_at, expires_at, last_seen_at, surface) "
                "VALUES (:h, :u, :c, :e, :c, :s)"
            ),
            {
                "h": _session_hash(session_token),
                "u": user_id,
                "c": at,
                "e": at + timedelta(seconds=ABSOLUTE_TIMEOUT_S),
                # Passed explicitly. The column has no default, so an omission
                # here would be a NOT NULL violation rather than a silent
                # website-domain row.
                "s": SURFACE_STREAMLIT,
            },
        )

        db.commit()
        return session_token
    except Exception:
        # Covers the invariant that matters most: no handoff is ever left
        # consumed without a session to show for it.
        db.rollback()
        raise
    finally:
        db.close()
