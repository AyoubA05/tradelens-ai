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
"""

from __future__ import annotations

import base64
import hmac
import json
import os
import secrets as _pysecrets
import time

from src.tradelens.ui.components.theme import (
    BORDER,
    HEADING_FONT,
    MONO_FONT,
    SURFACE,
    TEAL,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

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
_SIGNUP_ERR = "_signup_error"
_SIGNUP_OK = "_signup_ok"

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


def _render_login_form(st) -> None:
    with st.form("tl_login", clear_on_submit=False):
        username = st.text_input("Username", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")
        submitted = st.form_submit_button("Sign In", use_container_width=True)

    if submitted:
        # Belt-and-braces: no authentication error may escape and crash the
        # Streamlit script (the localhost "click login → crash" report). Any
        # failure becomes a normal "incorrect credentials" rejection.
        try:
            ok, uname, uid = authenticate_login(username, password)
        except Exception:  # noqa: BLE001 — never let auth errors crash the page
            ok, uname, uid = False, None, None
        if ok:
            st.session_state[_AUTH_KEY] = True
            st.session_state[_USER_KEY] = uname
            st.session_state[_UID_KEY] = uid
            st.session_state.pop(_ERROR_KEY, None)
            st.rerun()
        else:
            st.session_state[_ERROR_KEY] = True

    if st.session_state.get(_ERROR_KEY):
        st.error("Incorrect username or password.")

    if signup_enabled():
        if st.button("Create Account", key="show_signup", use_container_width=True):
            st.session_state[_MODE_KEY] = "signup"
            st.session_state.pop(_ERROR_KEY, None)
            st.rerun()


def _render_signup_form(st) -> None:
    st.caption("Create your account — an invite code is required.")
    show = st.checkbox("Show password", key="signup_show")
    ptype = "default" if show else "password"
    with st.form("tl_signup", clear_on_submit=False):
        username = st.text_input("Username", key="signup_username")
        password = st.text_input("Password", type=ptype, key="signup_password")
        confirm = st.text_input("Confirm Password", type=ptype, key="signup_confirm")
        invite = st.text_input(
            "Invite Code — required to create an account", key="signup_invite"
        )
        submitted = st.form_submit_button("Create Account", use_container_width=True)

    if submitted:
        error = process_signup(username, password, confirm, invite)
        if error:
            st.session_state[_SIGNUP_ERR] = error
        else:
            st.session_state[_SIGNUP_OK] = True
            st.session_state[_MODE_KEY] = "login"
            st.session_state.pop(_SIGNUP_ERR, None)
            st.rerun()

    if st.session_state.get(_SIGNUP_ERR):
        st.error(st.session_state[_SIGNUP_ERR])

    if st.button("← Back to Sign In", key="back_to_login", use_container_width=True):
        st.session_state[_MODE_KEY] = "login"
        st.session_state.pop(_SIGNUP_ERR, None)
        st.rerun()


# ---------------------------------------------------------------------------
# Landing page (pre-login). Scoped .tl-land-* CSS only — never bare tags (R1).
# Built from the design plan in docs/landing_audit.md: dark, left-aligned,
# asymmetric hero + feature band + one CTA. Identity preserved from theme.py.
# ---------------------------------------------------------------------------

# Line-style SVG icons (stroke only, teal — no icon-in-colored-circle, no emoji).
_IC_SHOT = (
    '<svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#20808D" '
    'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
    '<rect x="3" y="6" width="18" height="13" rx="2"/>'
    '<circle cx="12" cy="12.5" r="3.2"/><path d="M8 6 l1.5 -2 h5 L16 6"/></svg>'
)
_IC_CHART = (
    '<svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#20808D" '
    'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M4 20 V10"/><path d="M10 20 V4"/><path d="M16 20 v-8"/>'
    '<path d="M3 20 h18"/></svg>'
)
_IC_REVIEW = (
    '<svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#20808D" '
    'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M5 4 h11 l3 3 v13 a0 0 0 0 1 0 0 H5 z"/>'
    '<path d="M8 11 h8"/><path d="M8 15 h5"/></svg>'
)

# Signature element: a rising equity curve (the trader's own artifact), the one
# bold thing on the page. Solid teal stroke + faint solid-alpha fill (no gradient).
_EQUITY_SVG = (
    '<svg viewBox="0 0 320 110" width="100%" height="92" preserveAspectRatio="none" '
    'role="img" aria-label="A rising equity curve">'
    '<path d="M0,96 L40,82 L72,90 L112,60 L150,70 L192,42 L230,52 L276,22 L320,30 '
    'L320,110 L0,110 Z" fill="rgba(32,128,141,0.12)"/>'
    '<path d="M0,96 L40,82 L72,90 L112,60 L150,70 L192,42 L230,52 L276,22 L320,30" '
    'fill="none" stroke="#20808D" stroke-width="2.5" stroke-linecap="round" '
    'stroke-linejoin="round"/></svg>'
)


def _landing_css() -> str:
    return f"""<style>
[data-testid='stSidebar']{{display:none}}
.tl-land-header{{display:flex;align-items:center;justify-content:space-between;
flex-wrap:wrap;gap:8px;margin:4px 0 26px 0}}
.tl-land-brand{{display:flex;align-items:center;gap:10px}}
.tl-land-word{{font-family:'{HEADING_FONT}',sans-serif;font-weight:700;
font-size:1.25rem;letter-spacing:-0.02em;color:{TEXT_PRIMARY}}}
.tl-land-tag{{color:{TEXT_MUTED};font-size:0.82rem}}
.tl-hero-h1{{font-family:'{HEADING_FONT}',sans-serif;font-weight:700;
font-size:clamp(1.9rem,4vw,3rem);line-height:1.08;letter-spacing:-0.03em;
color:{TEXT_PRIMARY};text-wrap:balance;max-width:16ch;margin:6px 0 0 0}}
.tl-hero-accent{{color:{TEAL}}}
.tl-hero-sub{{color:{TEXT_SECONDARY};font-size:1.02rem;line-height:1.6;
max-width:56ch;margin:16px 0 0 0}}
.tl-hero-scope{{display:inline-flex;align-items:flex-start;gap:8px;
border:1px solid {BORDER};border-radius:10px;padding:9px 12px;margin-top:18px;
color:{TEXT_MUTED};font-size:0.82rem;line-height:1.45;max-width:54ch}}
.tl-hero-scope b{{color:{TEXT_SECONDARY};font-weight:600}}
.tl-hero-sig{{margin-top:22px;opacity:0.95}}
.tl-auth-card{{background:{SURFACE};border:1px solid {BORDER};border-radius:14px;
padding:20px 20px 8px 20px}}
.tl-auth-title{{font-family:'{HEADING_FONT}',sans-serif;font-weight:600;
font-size:1.05rem;color:{TEXT_PRIMARY};margin:0}}
.tl-auth-sub{{color:{TEXT_MUTED};font-size:0.82rem;margin:4px 0 12px 0}}
.tl-feat-band{{border-top:1px solid {BORDER};margin-top:30px;padding-top:8px}}
.tl-feat-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
gap:26px;margin-top:14px}}
.tl-feat{{border-top:2px solid {TEAL};padding-top:14px;
transition:border-color 180ms ease}}
.tl-feat:hover{{border-color:{TEXT_SECONDARY}}}
.tl-feat-h{{font-family:'{HEADING_FONT}',sans-serif;font-weight:600;font-size:1rem;
color:{TEXT_PRIMARY};margin:10px 0 0 0}}
.tl-feat-p{{color:{TEXT_SECONDARY};font-size:0.9rem;line-height:1.55;margin:5px 0 0 0}}
.tl-badge{{display:inline-flex;align-items:center;gap:7px;
border:1px solid {TEAL};border-radius:999px;padding:3px 11px;
color:{TEXT_SECONDARY};font-family:'{MONO_FONT}',monospace;
font-size:0.72rem;letter-spacing:0.02em}}
.tl-badge-dot{{width:6px;height:6px;border-radius:50%;background:{TEAL}}}
.tl-land-foot{{display:flex;align-items:center;justify-content:space-between;
flex-wrap:wrap;gap:10px;border-top:1px solid {BORDER};margin-top:26px;
padding-top:14px;color:{TEXT_MUTED};font-size:0.8rem}}
@media (prefers-reduced-motion: reduce){{.tl-feat{{transition:none}}}}
</style>"""


def _landing_header_html() -> str:
    wordmark = (
        '<svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" '
        f'stroke="{TEAL}" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round" style="vertical-align:middle">'
        '<path d="M3 17 l5 -6 l4 3 l6 -8"/><path d="M3 21 h18"/></svg>'
    )
    return (
        '<div class="tl-land-header"><div class="tl-land-brand">'
        f'{wordmark}<span class="tl-land-word">TradeLens AI</span></div>'
        '<div class="tl-land-tag">Post-trade journal &amp; analytics · SMC / ICT</div>'
        "</div>"
    )


def _landing_hero_html() -> str:
    return (
        '<h1 class="tl-hero-h1">The post-trade journal that '
        '<span class="tl-hero-accent">reads your charts back to you.</span></h1>'
        '<p class="tl-hero-sub">Drop in a chart screenshot and TradeLens turns it '
        "into a structured, searchable journal — then shows you the patterns behind "
        "your wins and the leaks behind your losses.</p>"
        '<div class="tl-hero-scope"><span>'
        "<b>Reflection only.</b> TradeLens reviews the trade you already took. "
        "It does not generate signals, predictions, or trade advice.</span></div>"
        f'<div class="tl-hero-sig">{_EQUITY_SVG}</div>'
    )


def _landing_features_html() -> str:
    feats = [
        (
            _IC_SHOT,
            "Screenshot-first journaling",
            "Add a TradingView screenshot and the AI reads the asset, session, "
            "setup, and bias. You confirm every field before it's saved.",
        ),
        (
            _IC_CHART,
            "SMC / ICT analytics",
            "Win rate, profit factor, R:R, drawdown, and P&amp;L by session and "
            "setup — grouped into clear sections, not a wall of numbers.",
        ),
        (
            _IC_REVIEW,
            "Weekly AI review",
            "An automatic written review of your week and the behavioral patterns "
            "in your journal, so you walk into the next session knowing your edge.",
        ),
    ]
    cells = "".join(
        f'<div class="tl-feat">{ic}<div class="tl-feat-h">{title}</div>'
        f'<p class="tl-feat-p">{body}</p></div>'
        for ic, title, body in feats
    )
    return f'<div class="tl-feat-band"><div class="tl-feat-grid">{cells}</div></div>'


def _landing_footer_html() -> str:
    return (
        '<div class="tl-land-foot">'
        '<span class="tl-badge"><span class="tl-badge-dot"></span>Private beta</span>'
        "<span>Built for traders who review the tape — never financial advice.</span>"
        "</div>"
    )


def _render_login() -> None:
    """Render the pre-login landing page: hero + features + the sign-in panel."""
    import streamlit as st

    st.markdown(_landing_css(), unsafe_allow_html=True)
    st.markdown(_landing_header_html(), unsafe_allow_html=True)

    hero, panel = st.columns([1.35, 1], gap="large")
    with hero:
        st.markdown(_landing_hero_html(), unsafe_allow_html=True)
    with panel:
        signup = st.session_state.get(_MODE_KEY) == "signup"
        st.markdown(
            '<div class="tl-auth-card"><p class="tl-auth-title">'
            + ("Create your account" if signup else "Sign in to your journal")
            + '</p><p class="tl-auth-sub">'
            + (
                "An invite code is required."
                if signup
                else "Pick up where you left off."
            )
            + "</p></div>",
            unsafe_allow_html=True,
        )
        if st.session_state.pop(_SIGNUP_OK, False):
            st.success("Account created. Sign in below.")
        if signup:
            _render_signup_form(st)
        else:
            _render_login_form(st)

    st.markdown(_landing_features_html(), unsafe_allow_html=True)
    st.markdown(_landing_footer_html(), unsafe_allow_html=True)


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
    _render_login()
    st.stop()


def render_logout_button() -> None:
    """Render a logout control (intended for the sidebar)."""
    import streamlit as st

    if st.button("Sign out", key="tl_logout", use_container_width=True):
        st.session_state[_AUTH_KEY] = False
        for key in (_USER_KEY, _UID_KEY, _ERROR_KEY, _MODE_KEY, _TOKEN_KEY):
            st.session_state.pop(key, None)
        st.query_params.pop(_TOKEN_PARAM, None)
        st.rerun()


def current_user() -> str | None:
    """The signed-in username, or None."""
    import streamlit as st

    return st.session_state.get(_USER_KEY)


def current_user_id() -> int | None:
    """The signed-in user's DB id (None for the secrets-fallback legacy user)."""
    import streamlit as st

    return st.session_state.get(_UID_KEY)
