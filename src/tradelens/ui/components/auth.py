"""
Password gate for TradeLens AI (Session A).

Single-user access control. Credentials come from Streamlit secrets / environment
(TRADELENS_USERNAME, TRADELENS_PASSWORD) — never hardcoded inline. A clearly
labeled demo fallback (demo / tradelens2025) keeps the public deploy usable when
no secrets are set; override it by setting the secrets.

Public surface:
    require_auth()          gate placed at the top of every page (after inject_css)
    render_logout_button()  sidebar logout control
    is_authenticated()      bool read of the session flag
    verify_credentials()    pure check, unit-tested

Credential reading is env-first so it is testable without Streamlit; st.secrets is
consulted as a fallback the same way config.py bridges ANTHROPIC_API_KEY.

Presentation (the focused auth card) lives in auth_screen.py — this module is
logic only (SP3 split).
"""

from __future__ import annotations

import base64
import hmac
import json
import os
import secrets as _pysecrets
import time

# Labeled fallback for a demo-only deployment. Real deployments set the secrets
# below and these are never used. This is NOT a hardcoded production credential —
# it is overridden by TRADELENS_USERNAME / TRADELENS_PASSWORD whenever they exist.
_DEFAULT_USERNAME = "demo"
_DEFAULT_PASSWORD = "tradelens2025"

_AUTH_KEY = "authenticated"
_USER_KEY = "current_user"
_UID_KEY = "current_user_id"
_ERROR_KEY = "_login_error"
_MODE_KEY = "_auth_mode"  # "login" | "signup"

# Reload-persistent session token (Item 1). st.session_state is wiped on a full
# browser reload, which used to boot the trader back to the login page ("the
# dashboard logged me out"). A signed, expiring token in the URL query params
# survives the reload and restores the session in require_auth().
#
# Security tradeoff (acknowledged): Streamlit has no native cookie-write API, so
# the token rides in the URL, where it could leak via copied links or browser
# history. Mitigations: HMAC-signed (unforgeable), short 24h TTL with sliding
# rotation for active sessions, revoked on logout, and dead after any server
# restart unless TRADELENS_SESSION_SECRET is configured.
_TOKEN_PARAM = "auth"
_TOKEN_KEY = "_auth_token"
_TOKEN_TTL_S = 24 * 3600  # short-lived; rotated while the trader stays active
_PROCESS_SECRET: bytes | None = None


def _session_secret() -> bytes:
    """Signing key for session tokens.

    Set TRADELENS_SESSION_SECRET (env/secrets) to keep sessions valid across app
    restarts; otherwise a random per-process key is used, so a server restart
    simply requires signing in again (tokens can never be forged offline).
    """
    global _PROCESS_SECRET
    configured = _read_secret("TRADELENS_SESSION_SECRET", "")
    if configured:
        return configured.encode()
    if _PROCESS_SECRET is None:
        _PROCESS_SECRET = _pysecrets.token_bytes(32)
    return _PROCESS_SECRET


def _issue_token(username, user_id, now: float | None = None) -> str:
    """Signed `payload.signature` token carrying (username, user_id, expiry)."""
    payload = {
        "u": username,
        "i": user_id,
        "e": int((now if now is not None else time.time()) + _TOKEN_TTL_S),
    }
    raw = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).decode()
    sig = hmac.new(_session_secret(), raw.encode(), "sha256").hexdigest()
    return f"{raw}.{sig}"


def _verify_token(token, now: float | None = None):
    """Return (username, user_id) for a valid, unexpired token — else None."""
    if not token or "." not in str(token):
        return None
    raw, _, sig = str(token).rpartition(".")
    expected = hmac.new(_session_secret(), raw.encode(), "sha256").hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(raw.encode()))
    except Exception:  # noqa: BLE001 — any malformed payload is just invalid
        return None
    if int(payload.get("e", 0)) < (now if now is not None else time.time()):
        return None
    return payload.get("u"), payload.get("i")


def _try_restore(st) -> None:
    """Rebuild the session from the signed URL token after a full page reload."""
    verified = _verify_token(st.query_params.get(_TOKEN_PARAM))
    if verified is None:
        return
    username, uid = verified
    st.session_state[_AUTH_KEY] = True
    st.session_state[_USER_KEY] = username
    st.session_state[_UID_KEY] = uid
    st.session_state[_TOKEN_KEY] = st.query_params.get(_TOKEN_PARAM)


def _persist_token(st) -> None:
    """Keep the current URL carrying a valid token so any reload survives.

    Sliding rotation: a token inside its last half-TTL is re-issued, so an
    active trader never expires mid-session while an abandoned/leaked URL
    dies within 24h.
    """
    token = st.session_state.get(_TOKEN_KEY)
    if not token or _verify_token(token, now=time.time() + _TOKEN_TTL_S / 2) is None:
        token = _issue_token(
            st.session_state.get(_USER_KEY), st.session_state.get(_UID_KEY)
        )
        st.session_state[_TOKEN_KEY] = token
    if st.query_params.get(_TOKEN_PARAM) != token:
        st.query_params[_TOKEN_PARAM] = token


def _read_secret(name: str, default: str) -> str:
    """Read a secret: environment first, then st.secrets, then the default.

    Wrapped defensively — st.secrets raises if no secrets file exists, which is
    normal in tests, so any failure simply falls through to the default.
    """
    val = os.getenv(name)
    if val:
        return str(val)
    try:
        import streamlit as st

        secret = st.secrets.get(name, None)
        if secret:
            return str(secret)
    except Exception:  # noqa: BLE001 — missing secrets file is expected
        pass
    return default


def expected_credentials() -> tuple[str, str]:
    """The (username, password) the app will accept this run."""
    return (
        _read_secret("TRADELENS_USERNAME", _DEFAULT_USERNAME),
        _read_secret("TRADELENS_PASSWORD", _DEFAULT_PASSWORD),
    )


def verify_credentials(username: str | None, password: str | None) -> bool:
    """Constant-time check of submitted credentials against the configured pair."""
    exp_user, exp_pass = expected_credentials()
    user_ok = hmac.compare_digest(str(username or ""), exp_user)
    pass_ok = hmac.compare_digest(str(password or ""), exp_pass)
    return user_ok and pass_ok


# ---------------------------------------------------------------------------
# Multi-user (Session B): DB users with a secrets fallback + invite-code signup
# ---------------------------------------------------------------------------


def invite_code() -> str:
    """The configured signup invite code, or "" when signup is disabled."""
    return _read_secret("TRADELENS_INVITE_CODE", "")


def signup_enabled() -> bool:
    """Signup is offered only when an invite code is configured."""
    return bool(invite_code())


def authenticate_login(username, password):
    """Resolve a login attempt to ``(ok, username, user_id)``.

    DB users take precedence: once the users table has rows, only bcrypt DB users
    can sign in. While it is empty, fall back to the secrets credentials (whose
    user_id is None — legacy single-user trades).
    """
    from src.tradelens.services import users

    try:
        has_db_users = users.users_exist()
    except Exception:  # noqa: BLE001 — a DB hiccup must not lock everyone out
        has_db_users = False

    if has_db_users:
        # Guard the DB query/bcrypt path the same way users_exist() is guarded:
        # this branch only runs once accounts exist (localhost dev DB), never on a
        # fresh Cloud deploy, so an unguarded error here is the localhost-only
        # "login crash". A failure falls through to a normal rejection, not a crash.
        try:
            user = users.authenticate(str(username or ""), str(password or ""))
        except Exception:  # noqa: BLE001 — a DB/bcrypt hiccup must not crash login
            user = None
        if user is not None:
            return True, user.username, user.id
        return False, None, None

    if verify_credentials(username, password):
        return True, str(username), None
    return False, None, None


def validate_signup(username, password, confirm, invite) -> str | None:
    """Return an error message for an invalid signup, or None when valid."""
    from src.tradelens.services import users

    if not users.is_valid_username(str(username or "")):
        return "Username must be 3–20 characters: letters, numbers, underscore."
    if users.username_taken(str(username)):
        return "Username already taken."
    if len(str(password or "")) < users.MIN_PASSWORD_LEN:
        return f"Password must be at least {users.MIN_PASSWORD_LEN} characters."
    if password != confirm:
        return "Passwords do not match."
    expected = invite_code()
    if not expected or not hmac.compare_digest(str(invite or ""), expected):
        return "Invalid invite code."
    return None


def process_signup(username, password, confirm, invite) -> str | None:
    """Validate + create a user. Returns an error message, or None on success."""
    from src.tradelens.services import users

    error = validate_signup(username, password, confirm, invite)
    if error:
        return error
    users.create_user(str(username), str(password))
    return None


# ---------------------------------------------------------------------------
# Streamlit-facing helpers (imported lazily so the module stays import-light)
# ---------------------------------------------------------------------------


def is_authenticated() -> bool:
    import streamlit as st

    return bool(st.session_state.get(_AUTH_KEY, False))


def require_auth() -> None:
    """Gate: if not signed in, render the login page and halt the script.

    Call once near the top of every page, right after inject_css(). When the user
    is authenticated this is a fast no-op.
    """
    import streamlit as st

    if not is_authenticated():
        # A full reload wipes st.session_state — the signed URL token survives.
        _try_restore(st)
    if is_authenticated():
        # Scope correction memory to the signed-in user for this script run, so
        # the few-shot injection in ai_client never mixes traders' corrections.
        from src.tradelens.services.corrections import set_corrections_user

        set_corrections_user(st.session_state.get(_UID_KEY))
        _persist_token(st)
        return
    # Lazy import: auth_screen imports logic from this module, so a top-level
    # import here would be circular (same pattern sidebar.py uses).
    from src.tradelens.ui.components.auth_screen import render_auth_screen

    render_auth_screen()
    st.stop()


def sign_out(rerun: bool = True) -> None:
    """Clear the session and the persisted token.

    Extracted so account deletion can end the session too: leaving a
    signed-in session pointing at a user row that no longer exists would
    put the app in a state nothing else expects.
    """
    import streamlit as st

    st.session_state[_AUTH_KEY] = False
    for key in (_USER_KEY, _UID_KEY, _ERROR_KEY, _MODE_KEY, _TOKEN_KEY):
        st.session_state.pop(key, None)
    st.query_params.pop(_TOKEN_PARAM, None)
    if rerun:
        st.rerun()


def render_logout_button() -> None:
    """Render a logout control (intended for the sidebar)."""
    import streamlit as st

    if st.button("Sign out", key="tl_logout", width="stretch"):
        sign_out()


def current_user() -> str | None:
    """The signed-in username, or None."""
    import streamlit as st

    return st.session_state.get(_USER_KEY)


def current_user_id() -> int | None:
    """The signed-in user's DB id (None for the secrets-fallback legacy user)."""
    import streamlit as st

    return st.session_state.get(_UID_KEY)
