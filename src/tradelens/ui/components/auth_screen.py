"""
SP3 — presentation for the pre-login auth screen.

Split out of auth.py, which keeps all logic (tokens, bcrypt, signup rules).
This module owns every pixel: the focused card, its scoped CSS, the backdrop,
and the motion. Scoped .tl-auth-* selectors only — styling bare tags breaks
Streamlit widgets and contrast.
"""

from __future__ import annotations

from html import escape

from src.tradelens.ui.design_system import (
    TL_BG,
    TL_BORDER,
    TL_DANGER,
    TL_DANGER_DIM,
    TL_PRIMARY,
    TL_SURFACE,
    TL_TEXT,
    TL_TEXT_MUTED,
    get_asset_as_base64,
)

# Marketing-site URL (same placeholder drill as site/main.js APP_URL).
SITE_URL = "https://www.tradelens-ai.example"  # TODO: swap at deploy

_EASE = "cubic-bezier(0.16, 1, 0.3, 1)"

_LOGO_SVG = (
    '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" '
    f'stroke="{TL_PRIMARY}" stroke-width="1.6" stroke-linecap="round" '
    'stroke-linejoin="round" aria-hidden="true">'
    '<circle cx="12" cy="12" r="9"/>'
    '<path d="M8 14.5V11"/><path d="M12 15.5V8.5"/><path d="M16 13V10"/>'
    "</svg>"
)


def auth_css() -> str:
    """Scoped styles for the focused auth card."""
    bg = get_asset_as_base64("auth_bg.webp")
    backdrop = (
        f"background-image:url(data:image/webp;base64,{bg});"
        if bg
        else f"background-color:{TL_BG};"
    )
    return f"""<style>
/* SP3 auth screen — scoped .tl-auth-* only. */
.tl-auth-bg {{
  position: fixed; inset: 0; z-index: 0;
  {backdrop}
  background-size: cover; background-position: 62% center;
  opacity: 0.28;
}}
.tl-auth-scrim {{
  position: fixed; inset: 0; z-index: 0;
  /* Token-derived, not the marketing site's #0d1117 — the app palette is
     TL_BG. Mixing the two palettes is exactly the drift SP3 removes. */
  background: linear-gradient(180deg, {TL_BG}d1, {TL_BG} 92%);
}}
.tl-auth-card {{
  position: relative; z-index: 1;
  max-width: 420px; margin: 6vh auto 0;
  background: {TL_SURFACE};
  border: 1px solid {TL_BORDER};
  border-radius: 16px;
  padding: 30px 30px 22px;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.55);
}}
.tl-auth-brand {{ display: flex; align-items: center; gap: 10px; }}
.tl-auth-word {{ font-weight: 700; font-size: 1.05rem; color: {TL_TEXT};
  letter-spacing: -0.01em; }}
.tl-auth-word em {{ font-style: normal; color: {TL_PRIMARY}; }}
.tl-auth-title {{ font-size: 1.5rem; font-weight: 700; color: {TL_TEXT};
  letter-spacing: -0.02em; margin: 18px 0 4px; }}
.tl-auth-sub {{ color: {TL_TEXT_MUTED}; font-size: 0.9rem; margin-bottom: 18px; }}
.tl-auth-err {{
  margin-top: 12px; padding: 10px 13px; border-radius: 9px;
  border: 1px solid {TL_DANGER}59; background: {TL_DANGER_DIM};
  color: {TL_TEXT}; font-size: 0.85rem; line-height: 1.45;
}}
.tl-auth-ok {{
  margin-top: 12px; padding: 10px 13px; border-radius: 9px;
  border: 1px solid {TL_PRIMARY}59; background: {TL_PRIMARY}1f;
  color: {TL_TEXT}; font-size: 0.85rem; line-height: 1.45;
}}
.tl-auth-note {{
  margin-top: 18px; padding-top: 14px; border-top: 1px solid {TL_BORDER};
  color: {TL_TEXT_MUTED}; font-size: 0.78rem; line-height: 1.5;
}}
.tl-auth-note b {{ color: {TL_TEXT}; font-weight: 600; }}
.tl-auth-back {{ display: inline-block; margin-top: 10px; color: {TL_TEXT_MUTED};
  font-size: 0.78rem; text-decoration: none; }}
.tl-auth-back:hover {{ color: {TL_PRIMARY}; }}
@media (max-width: 640px) {{
  .tl-auth-card {{ margin: 2vh 16px 0; padding: 24px 20px 18px; }}
}}
@media (prefers-reduced-motion: no-preference) {{
  .tl-auth-card {{ animation: tl-auth-in 250ms {_EASE} both; }}
  @keyframes tl-auth-in {{
    from {{ opacity: 0; transform: scale(0.98); }}
    to   {{ opacity: 1; transform: none; }}
  }}
  .tl-auth-err {{ animation: tl-auth-fade 200ms {_EASE} both; }}
  @keyframes tl-auth-fade {{
    from {{ opacity: 0; }}
    to   {{ opacity: 1; }}
  }}
}}
</style>"""


def brand_html(logo_b64: str = "") -> str:
    """Compact brand lockup for the card header."""
    mark = (
        f'<img src="data:image/png;base64,{logo_b64}" alt="" width="26" height="26" '
        'style="border-radius:6px;display:block" />'
        if logo_b64
        else _LOGO_SVG
    )
    return (
        f'<div class="tl-auth-brand">{mark}'
        '<span class="tl-auth-word">TradeLens&nbsp;<em>AI</em></span></div>'
    )


def compliance_html() -> str:
    """Scope note. Copy is load-bearing (CLAUDE.md) — do not reword."""
    return (
        '<div class="tl-auth-note"><b>Reflection only.</b> TradeLens reviews the '
        "trade you already took. It does not generate signals, predictions, or "
        "trade advice."
        f'<br><a class="tl-auth-back" href="{escape(SITE_URL)}">'
        "&larr; Back to tradelens-ai.com</a></div>"
    )


_MODE_KEY = "_auth_mode"  # "login" | "signup"
_ERROR_KEY = "_login_error"
_SIGNUP_ERR = "_signup_error"
_SIGNUP_OK = "_signup_ok"
_TOGGLE_KEY = "tl_auth_mode_toggle"
_FLIP_KEY = "_auth_flip_to_login"


def _error_html(message: str) -> str:
    """Error region. aria-live so screen readers announce it (WCAG)."""
    return (
        '<div class="tl-auth-err" role="alert" aria-live="polite">'
        f"{escape(message)}</div>"
    )


def _ok_html(message: str) -> str:
    """Success region (e.g. account created), same aria-live treatment."""
    return (
        '<div class="tl-auth-ok" role="status" aria-live="polite">'
        f"{escape(message)}</div>"
    )


def render_auth_screen() -> None:
    """Render the focused auth card. Logic stays in auth.py."""
    import streamlit as st

    from src.tradelens.ui.components.auth import (
        _AUTH_KEY,
        _UID_KEY,
        _USER_KEY,
        authenticate_login,
        process_signup,
        signup_enabled,
    )

    st.markdown(auth_css(), unsafe_allow_html=True)
    st.markdown('<div class="tl-auth-bg"></div>', unsafe_allow_html=True)
    st.markdown('<div class="tl-auth-scrim"></div>', unsafe_allow_html=True)

    # A keyed widget's stored state outlives `default=`, so a programmatic
    # signup→login flip must overwrite the toggle BEFORE it is instantiated.
    if st.session_state.pop(_FLIP_KEY, False):
        st.session_state[_TOGGLE_KEY] = "Sign in"
        st.session_state[_MODE_KEY] = "login"

    with st.container(key="tl_auth_card"):
        st.markdown(
            brand_html(get_asset_as_base64("logo_mark.png")), unsafe_allow_html=True
        )

        can_signup = signup_enabled()
        mode = st.session_state.get(_MODE_KEY, "login")
        if can_signup:
            choice = st.segmented_control(
                "Account",
                options=["Sign in", "Create account"],
                default="Create account" if mode == "signup" else "Sign in",
                key=_TOGGLE_KEY,
                label_visibility="collapsed",
            )
            mode = "signup" if choice == "Create account" else "login"
            st.session_state[_MODE_KEY] = mode

        if mode == "signup":
            st.markdown(
                '<div class="tl-auth-title">Create your account</div>'
                '<div class="tl-auth-sub">An invite code is required during '
                "beta.</div>",
                unsafe_allow_html=True,
            )
            with st.form("tl_signup", clear_on_submit=False):
                username = st.text_input("Username", key="signup_username")
                password = st.text_input(
                    "Password", type="password", key="signup_password"
                )
                confirm = st.text_input(
                    "Confirm password", type="password", key="signup_confirm"
                )
                invite = st.text_input("Invite code", key="signup_invite")
                submitted = st.form_submit_button("Create account", width="stretch")
            if submitted:
                with st.spinner("Creating your account…"):
                    error = process_signup(username, password, confirm, invite)
                if error:
                    st.session_state[_SIGNUP_ERR] = error
                else:
                    # Account created: return to Sign in with a success note.
                    st.session_state.pop(_SIGNUP_ERR, None)
                    st.session_state[_SIGNUP_OK] = True
                    st.session_state[_FLIP_KEY] = True
                    st.rerun()
            if st.session_state.get(_SIGNUP_ERR):
                st.markdown(
                    _error_html(st.session_state[_SIGNUP_ERR]), unsafe_allow_html=True
                )
        else:
            st.markdown(
                '<div class="tl-auth-title">Welcome back</div>'
                '<div class="tl-auth-sub">Sign in to review your trades.</div>',
                unsafe_allow_html=True,
            )
            if st.session_state.pop(_SIGNUP_OK, False):
                st.markdown(
                    _ok_html("Account created. Sign in below."),
                    unsafe_allow_html=True,
                )
            with st.form("tl_login", clear_on_submit=False):
                username = st.text_input("Username", key="login_username")
                password = st.text_input(
                    "Password", type="password", key="login_password"
                )
                submitted = st.form_submit_button("Sign in", width="stretch")
            if submitted:
                with st.spinner("Signing you in…"):
                    # authenticate_login -> (ok, username, user_id). Any auth
                    # error becomes a normal rejection, never a crash.
                    try:
                        ok, uname, uid = authenticate_login(username, password)
                    except Exception:  # noqa: BLE001 — never crash the login screen
                        ok, uname, uid = False, None, None
                if ok:
                    st.session_state[_AUTH_KEY] = True
                    st.session_state[_USER_KEY] = uname
                    st.session_state[_UID_KEY] = uid
                    st.session_state.pop(_ERROR_KEY, None)
                    st.rerun()
                else:
                    st.session_state[_ERROR_KEY] = (
                        "Incorrect username or password. "
                        "Check your details and try again."
                    )
            if st.session_state.get(_ERROR_KEY):
                st.markdown(
                    _error_html(st.session_state[_ERROR_KEY]), unsafe_allow_html=True
                )

        st.markdown(compliance_html(), unsafe_allow_html=True)
