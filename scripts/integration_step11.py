"""Step 11 integration: tenant isolation, IDOR, and the failure states.

Drives the *running* Next dev server over real HTTP and asserts against the
real dev database, so the request path under test is the one a browser uses:
same routes, same middleware, same cookies, same rate limiter.

Two disposable users are created and each tries to reach the other's data. The
interesting assertions are the negative ones — a test that only proves A can
read A's journal would pass on a system with no authorization at all.

Safety rules this script obeys, without exception:
  * dev-auth-migration only. Never production.
  * ``ayoub`` and ``Ayoub`` are read-only invariants and are never written to.
  * cleanup runs in ``finally``, children before parents.
  * no password, token, cookie or connection string is ever printed.

Usage (with the dev environment loaded and `next dev` running):
    python scripts/integration_step11.py
"""

from __future__ import annotations

import email
import hashlib
import json
import os
import re
import sys
import time
from email import policy

import requests
from sqlalchemy import text

# Read the environment BEFORE importing anything from the app. Importing the
# app pulls in Streamlit, which copies .streamlit/secrets.toml over os.environ
# and would silently replace the invite code and origins this script was told
# to use with whatever that file happens to contain.
SITE = os.environ.get("SITE_ORIGIN", "http://localhost:3000")
MAILBOX = os.environ.get("TRADELENS_DEV_MAILBOX", "")
INVITE = os.environ.get("TRADELENS_INVITE_CODE", "")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tradelens.db.session import SessionLocal  # noqa: E402
from src.tradelens.services import auth_sessions  # noqa: E402
from src.tradelens.services.auth_exchange import (  # noqa: E402
    exchange_handoff_for_streamlit_session,
)

HEADERS = {"Content-Type": "application/json", "Origin": SITE}

TAG = str(int(time.time()))[-8:]
PASSWORD_A = "Isolation-Alpha-2026!a"
PASSWORD_B = "Isolation-Bravo-2026!b"

FAILURES = 0
CREATED: list[int] = []


def check(label, ok, detail=""):
    global FAILURES
    if not ok:
        FAILURES += 1
    print(
        f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  -> {detail}" if detail else "")
    )


def db_scalar(sql, **params):
    db = SessionLocal()
    try:
        return db.execute(text(sql), params).scalar()
    finally:
        db.close()


def link_for(address: str, kind: str) -> str | None:
    """Pull the newest link of a kind out of the local SMTP sink."""
    if not MAILBOX or not os.path.exists(MAILBOX):
        return None
    pattern = re.compile(rf"https?://\S+/{kind}\?token=\S+")
    with open(MAILBOX, encoding="utf-8") as handle:
        records = [json.loads(line) for line in handle if line.strip()]
    for record in reversed(records):
        if not any(address in r for r in record["to"]):
            continue
        message = email.message_from_string(record["raw"], policy=policy.default)
        for part in message.walk():
            if part.get_content_type() == "text/plain":
                found = pattern.search(part.get_content())
                if found:
                    return found.group(0)
    return None


def signup(label: str, password: str) -> tuple[requests.Session, str, int]:
    """Create, verify and sign in one disposable account through the real API."""
    address = f"s11.{label}.{TAG}@example.invalid"
    session = requests.Session()

    response = session.post(
        f"{SITE}/api/auth/signup",
        headers=HEADERS,
        json={
            "email": address,
            "password": password,
            "fullName": f"Isolation {label.title()}",
            "birthday": "1993-03-03",
            "referralSource": "Friend",
            "referralOther": None,
            **({"invite": INVITE} if INVITE else {}),
        },
        timeout=30,
    )
    if response.status_code != 201:
        raise SystemExit(f"signup for {label} failed with {response.status_code}")

    user_id = db_scalar("SELECT id FROM users WHERE email = :e", e=address)
    CREATED.append(user_id)

    link = link_for(address, "verify-email")
    if not link:
        raise SystemExit(f"no verification mail captured for {label}")
    token = link.split("token=", 1)[1]
    verified = session.post(
        f"{SITE}/api/auth/verify", headers=HEADERS, json={"token": token}, timeout=30
    )
    if verified.status_code != 200:
        raise SystemExit(f"verification for {label} failed with {verified.status_code}")

    logged_in = session.post(
        f"{SITE}/api/auth/login",
        headers=HEADERS,
        json={"identifier": address, "password": password},
        timeout=30,
    )
    if logged_in.status_code != 200:
        raise SystemExit(f"login for {label} failed with {logged_in.status_code}")

    return session, address, user_id


def complete_onboarding(session: requests.Session, label: str) -> requests.Response:
    return session.post(
        f"{SITE}/api/auth/onboarding",
        headers=HEADERS,
        json={
            "fullName": f"Isolation {label.title()}",
            "birthday": "1993-03-03",
            "referralSource": "Friend",
            "referralOther": None,
        },
        timeout=30,
    )


def issue_handoff(session: requests.Session) -> str | None:
    """POST the handoff endpoint and return the raw token from the redirect."""
    response = session.post(
        f"{SITE}/api/auth/handoff",
        headers={"Origin": SITE},
        allow_redirects=False,
        timeout=30,
    )
    if response.status_code != 303:
        return None
    location = response.headers.get("location", "")
    return location.split("ht=", 1)[1] if "ht=" in location else None


def run() -> None:
    print("\n1. TWO DISPOSABLE ACCOUNTS, CREATED THROUGH THE REAL API")
    session_a, email_a, uid_a = signup("alpha", PASSWORD_A)
    session_b, email_b, uid_b = signup("bravo", PASSWORD_B)
    check("two distinct accounts exist", uid_a != uid_b, f"{uid_a} vs {uid_b}")

    complete_onboarding(session_a, "alpha")
    complete_onboarding(session_b, "bravo")

    print("\n2. IDOR — A SUPPLIED user_id MUST NEVER OVERRIDE THE SESSION")
    # Every shape an attacker would reach for: the field name the schema uses,
    # the camelCase the API uses, and the id of a real other account.
    for field in ("userId", "user_id", "id", "accountId", "sub"):
        response = session_a.post(
            f"{SITE}/api/auth/onboarding",
            headers=HEADERS,
            json={
                "fullName": "Overwritten By Alpha",
                "birthday": "1990-01-01",
                "referralSource": "Reddit",
                "referralOther": None,
                field: uid_b,
            },
            timeout=30,
        )
        victim = db_scalar("SELECT full_name FROM users WHERE id = :u", u=uid_b)
        check(
            f"onboarding ignores a `{field}` in the body",
            victim != "Overwritten By Alpha",
            f"status={response.status_code} victim_name={victim!r}",
        )

    # The same attempt through the query string, which some frameworks merge.
    session_a.post(
        f"{SITE}/api/auth/onboarding?userId={uid_b}",
        headers=HEADERS,
        json={
            "fullName": "Overwritten By Query",
            "birthday": "1990-01-01",
            "referralSource": "Reddit",
            "referralOther": None,
        },
        timeout=30,
    )
    check(
        "onboarding ignores a userId query parameter",
        db_scalar("SELECT full_name FROM users WHERE id = :u", u=uid_b)
        != "Overwritten By Query",
    )

    check(
        "A's own onboarding still wrote to A",
        db_scalar("SELECT full_name FROM users WHERE id = :u", u=uid_a)
        in ("Isolation Alpha", "Overwritten By Alpha", "Overwritten By Query"),
    )

    print("\n3. HANDOFF ISSUANCE IS BOUND TO THE SESSION, NOT THE REQUEST")
    ht_a = issue_handoff(session_a)
    check("A can mint a handoff", ht_a is not None)
    owner = db_scalar(
        "SELECT user_id FROM auth_handoffs WHERE token_hash = :h",
        h=hashlib.sha256((ht_a or "").encode()).hexdigest(),
    )
    check("the handoff belongs to A", owner == uid_a, f"{owner} vs {uid_a}")

    # A tries to mint one *for B* by every channel the endpoint could read.
    forged = session_a.post(
        f"{SITE}/api/auth/handoff?userId={uid_b}",
        headers=HEADERS,
        data=json.dumps({"userId": uid_b, "user_id": uid_b}),
        allow_redirects=False,
        timeout=30,
    )
    minted_for_b = db_scalar(
        "SELECT count(*) FROM auth_handoffs WHERE user_id = :u AND consumed_at IS NULL",
        u=uid_b,
    )
    check(
        "A cannot mint a handoff for B",
        minted_for_b == 0,
        f"status={forged.status_code} pending_for_b={minted_for_b}",
    )

    print("\n4. A REDEEMED HANDOFF OPENS A SESSION FOR ITS OWNER ONLY")
    # Re-minted deliberately. The forged POST above was still a *valid* issuance
    # for A, and only one handoff per account stays redeemable, so it retired
    # the earlier token — which is the invalidate-prior rule doing its job, not
    # a failure. Exchanging the stale one would test the wrong thing.
    ht_a = issue_handoff(session_a)
    token_a = exchange_handoff_for_streamlit_session(ht_a)
    check("A's handoff exchanges", token_a is not None)
    check(
        "the streamlit session resolves to A, not B",
        auth_sessions.restore_streamlit_session(token_a) == uid_a,
    )

    ht_b = issue_handoff(session_b)
    token_b = exchange_handoff_for_streamlit_session(ht_b)
    check("B's own handoff exchanges", token_b is not None)
    check(
        "B's session resolves to B",
        auth_sessions.restore_streamlit_session(token_b) == uid_b,
    )
    check("the two session tokens differ", token_a != token_b)

    print("\n5. CROSS-SURFACE AND CROSS-USER CREDENTIAL REUSE")
    # A's Streamlit bearer must not work as B's, and must not work as a website
    # cookie for anybody.
    check(
        "A's streamlit token is not a website session",
        db_scalar(
            "SELECT count(*) FROM auth_sessions WHERE token_hash = :h",
            h=hashlib.sha256(
                (auth_sessions.WEBSITE_DOMAIN + token_a).encode()
            ).hexdigest(),
        )
        == 0,
    )
    borrowed = requests.Session()
    borrowed.cookies.set("tl_session", token_a, domain="localhost")
    response = borrowed.post(
        f"{SITE}/api/auth/handoff",
        headers={"Origin": SITE},
        allow_redirects=False,
        timeout=30,
    )
    check(
        "A's streamlit bearer is rejected as a website cookie",
        response.status_code == 401,
        f"status={response.status_code}",
    )

    print("\n6. DATA OWNERSHIP IN THE APP'S OWN SERVICES")
    from src.tradelens.services.strategy import (
        get_active_strategy,
        upsert_strategy_profile,
    )
    from src.tradelens.services.trade_service import get_trades

    upsert_strategy_profile(uid_a, name=f"Alpha Playbook {TAG}")
    upsert_strategy_profile(uid_b, name=f"Bravo Playbook {TAG}")
    check(
        "each account reads back its own playbook",
        get_active_strategy(uid_a)["name"] == f"Alpha Playbook {TAG}"
        and get_active_strategy(uid_b)["name"] == f"Bravo Playbook {TAG}",
    )
    # Keyword, not positional: get_trades' first parameter is start_date and
    # its user filter defaults to *unscoped*, so a positional call silently
    # asks for every trade in the table. Every live call site passes the
    # keyword; only the archived pages do not.
    check(
        "A's journal is empty and not the legacy users'",
        len(get_trades(user_id=uid_a)) == 0,
    )
    check("B's journal is empty and not A's", len(get_trades(user_id=uid_b)) == 0)
    check(
        "the legacy trades exist but belong to neither",
        db_scalar(
            "SELECT count(*) FROM trades WHERE user_id NOT IN (:a, :b)",
            a=uid_a,
            b=uid_b,
        )
        > 0,
    )

    print("\n7. FAILURE STATES ARE INDISTINGUISHABLE AND NEVER LOOP")
    # Invalid, expired-shaped, and consumed all return None, not an exception
    # and not a partial success.
    check(
        "garbage handoff is rejected",
        exchange_handoff_for_streamlit_session("nope") is None,
    )
    check(
        "empty handoff is rejected", exchange_handoff_for_streamlit_session("") is None
    )
    check(
        "None handoff is rejected", exchange_handoff_for_streamlit_session(None) is None
    )
    check(
        "an already-consumed handoff is rejected",
        exchange_handoff_for_streamlit_session(ht_a) is None,
    )
    check(
        "a revoked streamlit session stops authenticating",
        auth_sessions.revoke_streamlit_session(token_b)
        and auth_sessions.restore_streamlit_session(token_b) is None,
    )
    check(
        "garbage session token is rejected",
        auth_sessions.restore_streamlit_session("x") is None,
    )

    # An inactive account cannot redeem an outstanding handoff.
    ht_late = issue_handoff(session_a)
    db = SessionLocal()
    try:
        db.execute(text("UPDATE users SET is_active = 0 WHERE id = :u"), {"u": uid_a})
        db.commit()
    finally:
        db.close()
    check(
        "a deactivated account cannot redeem its handoff",
        exchange_handoff_for_streamlit_session(ht_late) is None,
    )
    db = SessionLocal()
    try:
        db.execute(text("UPDATE users SET is_active = 1 WHERE id = :u"), {"u": uid_a})
        db.commit()
    finally:
        db.close()

    print("\n8. VERIFICATION AND RESET FAILURE STATES SPEAK WITH ONE VOICE")
    answers = set()
    for bad in ("not-a-token", "", "a" * 43):
        answers.add(
            requests.post(
                f"{SITE}/api/auth/verify",
                headers=HEADERS,
                json={"token": bad},
                timeout=30,
            ).text
        )
    check(
        "every rejected verification reads alike",
        len(answers) == 1,
        f"{len(answers)} variants",
    )

    answers = set()
    for bad in ("not-a-token", "", "a" * 43):
        answers.add(
            requests.post(
                f"{SITE}/api/auth/reset-password",
                headers=HEADERS,
                json={"token": bad, "password": "Whatever-Valid-2026!x"},
                timeout=30,
            ).text
        )
    check(
        "every rejected reset reads alike",
        len(answers) == 1,
        f"{len(answers)} variants",
    )

    print("\n9. LEGACY ACCOUNTS ARE UNTOUCHED BY ALL OF THE ABOVE")
    rows = db_scalar("SELECT count(*) FROM users WHERE username IN ('ayoub', 'Ayoub')")
    check("both legacy rows still present", rows == 2, str(rows))


def cleanup() -> None:
    """Children before parents. Runs whatever happened above."""
    print("\nCLEANUP")
    if not CREATED:
        print("  nothing to remove")
        return
    db = SessionLocal()
    try:
        for table in (
            "auth_sessions",
            "auth_handoffs",
            "email_verifications",
            "password_resets",
            "user_settings",
            "strategies",
            "trades",
            "corrections",
            "weekly_reviews",
            "ai_usage_log",
        ):
            try:
                db.execute(
                    text(f"DELETE FROM {table} WHERE user_id = ANY(:ids)"),
                    {"ids": CREATED},
                )
            except Exception:
                db.rollback()
                continue
        db.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": CREATED})
        # Rate-limit rows are keyed by hashed identifier, not user_id.
        db.execute(
            text(
                "DELETE FROM auth_attempts WHERE created_at > now() - interval '2 hours'"
            )
        )
        db.commit()
        print(
            f"  removed {len(CREATED)} disposable account(s) and their dependent rows"
        )
    finally:
        db.close()


def main() -> int:
    print(f"STEP 11 INTEGRATION  (tag {TAG})")
    try:
        run()
    finally:
        cleanup()

    db = SessionLocal()
    try:
        print("\nPOST-RUN STATE")
        print(
            f"  users            {db.execute(text('SELECT count(*) FROM users')).scalar()}"
        )
        names = [
            r[0]
            for r in db.execute(text("SELECT username FROM users ORDER BY id")).all()
        ]
        print(f"  usernames        {names}")
        for table in (
            "auth_sessions",
            "auth_handoffs",
            "auth_attempts",
            "email_verifications",
            "password_resets",
        ):
            print(
                f"  {table:<20} {db.execute(text(f'SELECT count(*) FROM {table}')).scalar()}"
            )
        for username in ("ayoub", "Ayoub"):
            digest = db.execute(
                text("SELECT password_hash FROM users WHERE username = :n"),
                {"n": username},
            ).scalar()
            print(
                f"  {username} fingerprint  "
                f"{hashlib.sha256(str(digest).encode()).hexdigest()[:16]}"
            )
    finally:
        db.close()

    print(
        "\n"
        + (
            "INTEGRATION PASSED"
            if FAILURES == 0
            else f"INTEGRATION FAILED ({FAILURES})"
        )
    )
    return 0 if FAILURES == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
