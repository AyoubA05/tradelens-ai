"""
Password gate for TradeLens AI (Session A).

Single-user access control. Credentials come from Streamlit secrets /
environment (TRADELENS_USERNAME, TRADELENS_PASSWORD) — never hardcoded inline
and with no fallback pair. When they are unset or blank the legacy path is
UNAVAILABLE rather than open: there is nothing to sign in with.

Two failures that look alike are kept apart here, because conflating them was
a real authentication bypass:

    users table queried, found empty  -> legacy login may apply, if configured
    users table could not be queried  -> AuthUnavailableError, no decision

Public surface:
    require_auth()            gate at the top of every page (after inject_css)
    render_logout_button()    sidebar logout control
    is_authenticated()        bool read of the session flag
    verify_credentials()      pure check, unit-tested
    legacy_login_configured() whether the legacy path exists at all
    AuthUnavailableError      raised when the user store cannot be consulted

Credential reading is env-first so it is testable without Streamlit; st.secrets is
consulted as a fallback the same way config.py bridges ANTHROPIC_API_KEY.

Presentation (the focused auth card) lives in auth_screen.py — this module is
logic only (SP3 split).
"""

from __future__ import annotations

import base64
import hmac
import json
import logging
import secrets as _pysecrets
import time

_log = logging.getLogger(__name__)


class AuthUnavailableError(RuntimeError):
    """The user store could not be consulted, so no decision can be made.

    Deliberately distinct from "these credentials are wrong". The old code
    could not tell the two apart, and that is what made the bypass possible:
    a failed lookup was indistinguishable from a database with no users in
    it, and the second of those legitimately falls back to legacy login.
    """


# There is NO fallback credential pair. There used to be — a demo username and
# password written as literals in this file, see `a0ef59b` — and
# `expected_credentials()` handed it out whenever the deployment secrets were
# unset. Combined with the fail-open below it meant a database outage on a real
# deployment downgraded login to a password published in the repository.
#
# The old literals are deliberately NOT quoted here. A guard in
# tests/test_auth_fail_closed.py asserts this module's source contains no such
# string, so writing one into a comment would fail the suite — which is the
# intended outcome: an auth module should hold no credential-shaped literal at
# all, and three contracts in this project have already been broken by a
# comment that spelled out the thing it was guarding against.
#
# Legacy single-user login is still supported, but only when it has been
# explicitly configured: both TRADELENS_USERNAME and TRADELENS_PASSWORD must
# be set and non-blank. Unset means the legacy path is unavailable, not that
# it is open with a default.

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
    from src.tradelens.settings_source import read_setting

    return read_setting(name, default)


def expected_credentials() -> tuple[str, str]:
    """The legacy (username, password) this deployment accepts.

    ``("", "")`` when the legacy path is not configured. The empty string is
    the honest answer: it means "nothing is configured", where the old
    default meant "everything is configured, with a password anyone can read".
    """
    return (
        _read_secret("TRADELENS_USERNAME", ""),
        _read_secret("TRADELENS_PASSWORD", ""),
    )


def legacy_login_configured() -> bool:
    """Whether legacy single-user login is available at all.

    Both halves must be present and non-blank. A deployment that sets only
    one of them has not configured legacy login; it has half-configured it,
    which must not authenticate anyone.

    Whitespace-only counts as blank. `TRADELENS_PASSWORD="   "` is what an
    empty value in a YAML secrets file or a mistyped CI variable looks like by
    the time it arrives here, and treating it as a configured password means
    three spaces sign somebody in.
    """
    exp_user, exp_pass = expected_credentials()
    return bool(exp_user.strip()) and bool(exp_pass.strip())


def verify_credentials(username: str | None, password: str | None) -> bool:
    """Constant-time check of submitted credentials against the configured pair.

    Returns False when the legacy path is unconfigured, BEFORE comparing
    anything. Without this an unset deployment compared the submission against
    ``("", "")``, so a blank username and blank password authenticated.

    The configured check strips, but the COMPARISON does not: a deployment
    whose real password legitimately begins or ends with a space must still be
    able to sign in with it exactly.
    """
    exp_user, exp_pass = expected_credentials()
    if not legacy_login_configured():
        return False
    # Both comparisons always run: `and` would short-circuit on the username
    # and leak, by timing, whether the username was the right one.
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
    can sign in. While it is genuinely empty, fall back to the legacy credentials
    (whose user_id is None — legacy single-user trades) IF they are configured.

    Raises ``AuthUnavailableError`` when the user store cannot be consulted.
    That is the whole point of this function's shape: a dependency failure is
    not an authentication mode. The old code turned the exception into
    ``has_db_users = False`` and carried on into the legacy branch, so a
    database outage silently changed which credentials the app accepted.
    """
    from src.tradelens.services import users

    try:
        has_db_users = users.users_exist()
    except Exception as exc:  # noqa: BLE001 — converted, never swallowed
        # Type name only. The message and traceback of a DB error routinely
        # carry the DSN, host, and the SQL that failed; none of that belongs
        # in a log line that a support process may forward onwards.
        _log.error(
            "Authentication unavailable: user lookup failed (%s)",
            type(exc).__name__,
        )
        raise AuthUnavailableError("user store unavailable") from exc

    if has_db_users:
        try:
            user = users.authenticate(str(username or ""), str(password or ""))
        except Exception as exc:  # noqa: BLE001 — converted, never swallowed
            _log.error(
                "Authentication unavailable: credential check failed (%s)",
                type(exc).__name__,
            )
            raise AuthUnavailableError("user store unavailable") from exc
        if user is not None:
            return True, user.username, user.id
        # No fallthrough. A deployment with accounts authenticates against
        # those accounts or not at all; dropping to the legacy path here would
        # hand a user_id=None session to whoever knew the legacy password.
        return False, None, None

    # The users table was queried successfully and is empty.
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


def _clear_session_state_for_sign_out(state) -> None:
    """Remove authentication and ephemeral Partner data from one session."""
    for key in (_AUTH_KEY, _USER_KEY, _UID_KEY, _ERROR_KEY, _MODE_KEY, _TOKEN_KEY):
        state.pop(key, None)

    # `_partner_` and not `_partner_pending_`: the narrower prefix named one
    # key and missed every other private one beside it. `_partner_queue`
    # carried the previous trader's unsent question in plain text and
    # `_partner_run` carried the counter that made it claimable, so signing
    # out and handing the browser to someone else left a question they never
    # asked ready to be sent as them. The prefix now covers the whole
    # namespace, which is what stops the next key being forgotten too;
    # `test_every_partner_session_key_is_covered_by_the_cleanup` holds it.
    partner_prefixes = ("partner_", "_partner_", "secondary_partner_")
    for key in list(state):
        if str(key).startswith(partner_prefixes):
            state.pop(key, None)


def sign_out(rerun: bool = True) -> None:
    """Clear the session and the persisted token.

    Extracted so account deletion can end the session too: leaving a
    signed-in session pointing at a user row that no longer exists would
    put the app in a state nothing else expects.
    """
    import streamlit as st

    _clear_session_state_for_sign_out(st.session_state)
    st.session_state[_AUTH_KEY] = False
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
