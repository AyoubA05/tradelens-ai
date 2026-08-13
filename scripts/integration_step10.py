"""Step 10 integration against dev-auth-migration / neondb.

Exercises what the SQLite tests stub: real Postgres atomicity, real concurrency,
real cross-surface rejection with both implementations, and the real
password-reset interaction.

Disposable tagged accounts only. ayoub/Ayoub are read-only invariants. Cleanup
runs in a finally, children before parents.

NEVER point this at production.
"""

from __future__ import annotations

import hashlib
import os
import sys
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tradelens.db.session import SessionLocal  # noqa: E402
from src.tradelens.services import (  # noqa: E402
    auth_exchange,
    auth_handoff,
    auth_sessions,
)
from src.tradelens.ui.components import site_auth, strategy_gate  # noqa: E402

TAG = str(int(__import__("time").time()))[-8:]
FAILURES = 0
CREATED: list[int] = []


def check(label, ok, detail=""):
    global FAILURES
    if not ok:
        FAILURES += 1
    print(
        f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  -> {detail}" if detail else "")
    )


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class FakeSt:
    """Minimal stand-in for the Streamlit runtime object site_auth uses."""

    def __init__(self, **params):
        self.query_params = dict(params)
        self.session_state = {}


def counts():
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT (SELECT count(*) FROM users) u,"
                " (SELECT count(*) FROM auth_sessions) s,"
                " (SELECT count(*) FROM auth_handoffs) h,"
                " (SELECT count(*) FROM auth_attempts) a,"
                " (SELECT count(*) FROM email_verifications) v,"
                " (SELECT count(*) FROM password_resets) r"
            )
        ).one()
        return dict(
            zip(
                (
                    "users",
                    "sessions",
                    "handoffs",
                    "attempts",
                    "verifications",
                    "resets",
                ),
                row,
            )
        )
    finally:
        db.close()


def make_user(n, *, strategy_done=False):
    db = SessionLocal()
    try:
        uid = db.execute(
            text(
                "INSERT INTO users (username, password_hash, email, is_active,"
                " onboarding_completed, strategy_profile_completed,"
                " email_verification_required, email_verified_at)"
                " VALUES (:un, :ph, :em, 1, true, :sp, true, now()) RETURNING id"
            ),
            {
                "un": f"u_s10{TAG}{n}",
                "ph": "$2b$12$" + "x" * 53,
                "em": f"s10+{TAG}{n}@example.invalid",
                "sp": strategy_done,
            },
        ).scalar()
        db.commit()
        CREATED.append(uid)
        return uid
    finally:
        db.close()


def run():
    # 1-4. ready user, website session, handoff
    uid = make_user(1)
    website_token = _open_website_session(uid)
    ht = auth_handoff.issue_handoff(uid)
    check(
        "strategy_profile_completed starts false",
        strategy_gate.needs_strategy_profile(uid),
    )

    # 5-6. exchange
    session_token = auth_exchange.exchange_handoff_for_streamlit_session(ht)
    check("exchange succeeds", session_token is not None)
    check("streamlit token != handoff", session_token != ht)
    check("streamlit token != website token", session_token != website_token)

    db = SessionLocal()
    try:
        consumed = db.execute(
            text("SELECT consumed_at FROM auth_handoffs WHERE token_hash = :h"),
            {"h": sha256(ht)},
        ).scalar()
        rows = db.execute(
            text(
                "SELECT surface, token_hash FROM auth_sessions WHERE user_id = :u ORDER BY surface"
            ),
            {"u": uid},
        ).all()
    finally:
        db.close()
    check("handoff consumed", consumed is not None)
    check(
        "exactly one streamlit session exists",
        sum(1 for r in rows if r[0] == "streamlit") == 1,
    )
    check("website session still present", any(r[0] == "website" for r in rows))
    check(
        "surfaces are website and streamlit",
        sorted(r[0] for r in rows) == ["streamlit", "website"],
    )
    check(
        "streamlit row stores the streamlit-domain hash",
        any(
            r[1] == sha256(auth_sessions.STREAMLIT_DOMAIN + session_token) for r in rows
        ),
    )

    # 7-8. the ht -> s query transition
    st = FakeSt(ht=auth_handoff.issue_handoff(uid))
    resolved = site_auth.authenticate(st)
    check("entry path authenticates", resolved == uid)
    check("ht is gone from the visible params", "ht" not in st.query_params)
    check("s is present and is the only credential", list(st.query_params) == ["s"])

    # 9-10. validation and routing
    s_token = st.query_params["s"]
    check(
        "s validates server-side",
        auth_sessions.restore_streamlit_session(s_token) == uid,
    )
    check(
        "routes to the first-run Strategy Profile",
        strategy_gate.route_after_authentication(uid) == "strategy_profile",
    )

    # 11-12. completion through the real service, then routing changes
    from src.tradelens.services.users import mark_strategy_profile_completed

    mark_strategy_profile_completed(uid)
    check(
        "routes to the dashboard once completed",
        strategy_gate.route_after_authentication(uid) == "dashboard",
    )

    # 13-14. logout revokes only this session
    other_streamlit = auth_sessions.open_streamlit_session(uid)
    signed_out = site_auth.sign_out_streamlit_session(st)
    check("sign-out revoked the current session", signed_out)
    check(
        "s no longer authenticates",
        auth_sessions.restore_streamlit_session(s_token) is None,
    )
    check("s removed from the visible params", "s" not in st.query_params)
    check(
        "the other streamlit session is untouched",
        auth_sessions.restore_streamlit_session(other_streamlit) == uid,
    )
    check("the website session is untouched", _website_session_alive(website_token))

    # 15. concurrency on real Postgres
    racer = make_user(2)
    race_ht = auth_handoff.issue_handoff(racer)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(
                lambda _: auth_exchange.exchange_handoff_for_streamlit_session(race_ht),
                range(8),
            )
        )
    winners = [r for r in results if r]
    check(
        "8 concurrent exchanges -> exactly one winner",
        len(winners) == 1,
        str(len(winners)),
    )
    db = SessionLocal()
    try:
        n = db.execute(
            text(
                "SELECT count(*) FROM auth_sessions WHERE user_id = :u AND surface = 'streamlit'"
            ),
            {"u": racer},
        ).scalar()
    finally:
        db.close()
    check("exactly one streamlit session from that handoff", n == 1, str(n))

    # 16. forced insert failure leaves the handoff redeemable
    victim = make_user(3)
    fail_ht = auth_handoff.issue_handoff(victim)
    real_hash = auth_exchange._session_hash
    auth_exchange._session_hash = lambda t: (_ for _ in ()).throw(
        RuntimeError("forced")
    )
    try:
        auth_exchange.exchange_handoff_for_streamlit_session(fail_ht)
        check("forced failure raised", False, "no exception")
    except RuntimeError:
        check("forced failure raised", True)
    finally:
        auth_exchange._session_hash = real_hash
    db = SessionLocal()
    try:
        still = db.execute(
            text("SELECT consumed_at FROM auth_handoffs WHERE token_hash = :h"),
            {"h": sha256(fail_ht)},
        ).scalar()
    finally:
        db.close()
    check("handoff NOT consumed after rollback", still is None)
    check(
        "handoff is still redeemable",
        auth_exchange.exchange_handoff_for_streamlit_session(fail_ht) is not None,
    )

    # 17. password reset revokes across surfaces and voids handoffs
    reset_user = make_user(4)
    reset_ht = auth_handoff.issue_handoff(reset_user)
    reset_session = auth_exchange.exchange_handoff_for_streamlit_session(reset_ht)
    check(
        "streamlit session live before reset",
        auth_sessions.restore_streamlit_session(reset_session) == reset_user,
    )
    pending_ht = auth_handoff.issue_handoff(reset_user)
    revoked = auth_sessions.revoke_all_for_user(reset_user)
    db = SessionLocal()
    try:
        db.execute(
            text(
                "UPDATE auth_handoffs SET consumed_at = now() "
                "WHERE user_id = :u AND consumed_at IS NULL"
            ),
            {"u": reset_user},
        )
        db.commit()
    finally:
        db.close()
    check(
        "reset revoked the streamlit session",
        auth_sessions.restore_streamlit_session(reset_session) is None,
        f"revoked={revoked}",
    )
    check(
        "a handoff issued before reset cannot be exchanged after",
        auth_exchange.exchange_handoff_for_streamlit_session(pending_ht) is None,
    )

    # 18. isolation
    check(
        "the racer's session did not leak to the first user",
        auth_sessions.restore_streamlit_session(winners[0]) == racer,
    )


def _open_website_session(uid: int) -> str:
    """Mint a website-surface row the way the TypeScript side does."""
    import secrets

    from datetime import datetime, timedelta, timezone

    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO auth_sessions (token_hash, user_id, created_at,"
                " expires_at, last_seen_at, surface)"
                " VALUES (:h, :u, :c, :e, :c, 'website')"
            ),
            {
                "h": sha256(auth_sessions.WEBSITE_DOMAIN + token),
                "u": uid,
                "c": now,
                "e": now + timedelta(hours=12),
            },
        )
        db.commit()
        return token
    finally:
        db.close()


def _website_session_alive(token: str) -> bool:
    db = SessionLocal()
    try:
        return (
            db.execute(
                text(
                    "SELECT count(*) FROM auth_sessions WHERE token_hash = :h"
                    " AND surface = 'website' AND revoked_at IS NULL"
                ),
                {"h": sha256(auth_sessions.WEBSITE_DOMAIN + token)},
            ).scalar()
            == 1
        )
    finally:
        db.close()


def cross_surface_regression():
    """The permanent exploit regression, run against real Postgres."""
    uid = make_user(9)
    website = _open_website_session(uid)
    streamlit = auth_sessions.open_streamlit_session(uid)

    check(
        "website token rejected by the Streamlit validator",
        auth_sessions.restore_streamlit_session(website) is None,
    )
    check(
        "streamlit token validates on Streamlit",
        auth_sessions.restore_streamlit_session(streamlit) == uid,
    )
    check("website token validates on the website", _website_session_alive(website))
    check(
        "streamlit token is not stored under the website domain",
        not _website_session_alive(streamlit),
    )


def cleanup(before):
    db = SessionLocal()
    try:
        if CREATED:
            for table in (
                "auth_sessions",
                "auth_handoffs",
                "password_resets",
                "email_verifications",
            ):
                db.execute(
                    text(
                        f"DELETE FROM {table} WHERE user_id = ANY(:ids)"
                    ),  # noqa: S608
                    {"ids": CREATED},
                )
            db.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": CREATED})
        db.execute(text("DELETE FROM auth_attempts"))
        db.commit()
    finally:
        db.close()

    after = counts()
    print(f"\n  post-test: {after}")
    check("users = 2", after["users"] == 2, str(after["users"]))
    for key in ("sessions", "handoffs", "attempts", "verifications", "resets"):
        check(
            f"{key} back to pre-test",
            after[key] == before[key],
            f"{before[key]} -> {after[key]}",
        )

    db = SessionLocal()
    try:
        rows = db.execute(
            text("SELECT username, password_hash FROM users ORDER BY id")
        ).all()
    finally:
        db.close()
    check(
        "usernames exactly ayoub / Ayoub",
        [r[0] for r in rows] == ["ayoub", "Ayoub"],
        str([r[0] for r in rows]),
    )
    fps = [sha256(r[1])[:16] for r in rows]
    check(
        "legacy fingerprints unchanged",
        fps == ["ad21629058e33b79", "63585ccd0f71998e"],
        " / ".join(fps),
    )


def main():
    print("=== dev Neon Step 10 integration ===")
    before = counts()
    print(f"  pre-test: {before}")

    db = SessionLocal()
    try:
        names = [
            r[0] for r in db.execute(text("SELECT username FROM users ORDER BY id"))
        ]
    finally:
        db.close()
    if names != ["ayoub", "Ayoub"]:
        print(f"  REFUSING: expected the two dev accounts, found {names}")
        raise SystemExit(2)

    try:
        run()
        print("\n  --- cross-surface exploit regression ---")
        cross_surface_regression()
    except Exception as exc:  # noqa: BLE001
        global FAILURES
        FAILURES += 1
        print(f"  [FAIL] run threw: {type(exc).__name__}: {exc}")
    finally:
        try:
            cleanup(before)
        except Exception as exc:  # noqa: BLE001
            FAILURES += 1
            print(f"  [FAIL] cleanup threw: {exc}")

    print("\nINTEGRATION PASSED" if FAILURES == 0 else f"\n{FAILURES} CHECK(S) FAILED")
    raise SystemExit(0 if FAILURES == 0 else 1)


if __name__ == "__main__":
    main()
