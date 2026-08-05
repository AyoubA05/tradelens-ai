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
    TL_SURFACE_CANVAS,
    TL_Z_BASE,
    TL_Z_RAISED,
    TL_LINE_HAIRLINE,
    TL_DANGER,
    TL_DANGER_DIM,
    TL_PRIMARY,
    TL_SURFACE_PANEL,
    TL_SURFACE_ELEVATED,
    TL_CONTENT_PRIMARY,
    TL_CONTENT_SECONDARY,
    get_asset_as_base64,
)

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
        else f"background-color:{TL_SURFACE_CANVAS};"
    )
    return f"""<style>
/* SP3 auth screen — scoped .tl-auth-* only. */
.tl-auth-bg {{
  position: fixed; inset: 0; z-index: {TL_Z_BASE};
  {backdrop}
  background-size: cover; background-position: 62% center;
  opacity: 0.28;
}}
.tl-auth-scrim {{
  position: fixed; inset: 0; z-index: {TL_Z_BASE};
  /* Token-derived, not the marketing site's #0d1117 — the app palette is
     TL_SURFACE_CANVAS. Mixing the two palettes is exactly the drift SP3 removes. */
  background: linear-gradient(180deg, {TL_SURFACE_CANVAS}d1, {TL_SURFACE_CANVAS} 92%);
}}
/* Streamlit-specific: the auth screen renders pre-login only, so these
   testid-scoped paddings never leak into the app pages. */
[data-testid="stMainBlockContainer"] {{
  padding-top: 2.5rem;
}}
/* The card provides the chrome — the st.form inside it must not draw its
   own box-in-a-box border. */
.st-key-tl_auth_card [data-testid="stForm"] {{
  border: none;
  padding: 0;
}}
/* The keyed st.container renders as .st-key-tl_auth_card; .tl-auth-card is
   the semantic alias kept for markup and tests. */
.st-key-tl_auth_card,
.tl-auth-card {{
  /* The card sits above the photograph and its scrim, both of which are at
     the base tier. Raised, not a bare 1: the ordering is the same, but it is
     now stated in the one scale every other layer is measured against. */
  position: relative; z-index: {TL_Z_RAISED};
  max-width: 420px; margin: 6vh auto 0;
  background: {TL_SURFACE_PANEL};
  border: 1px solid {TL_LINE_HAIRLINE};
  border-radius: 16px;
  padding: 30px 30px 22px;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.55);
}}
/* --- native Streamlit widgets inside the auth card ---
   These rules were written when the workspace base was light. The base is now
   dark everywhere, so most of this block was expected to be redundant — and
   measured in a real browser, most of it is. With the block removed, the card,
   inputs, labels and expander summary render *identically*: same
   rgb(236,245,244) on rgb(16,27,32), 15.78:1, zero exceptions.

   Two rules still do work, which is why the block stays:

     button text   with: rgb(145,163,167)   without: rgb(236,245,244)
     placeholder   with: rgb(145,163,167)   without: rgba(236,245,244,0.6)

   The button one is load-bearing, not cosmetic. Sign-in has one filled primary
   action; the secondary control has to stay quieter than it. Without the
   override Streamlit paints both at full content weight and the card reads as
   two primaries — the exact failure the rail's one-primary rule exists to
   prevent.

   Narrowing this to those two rules is a change to the auth surface, which
   Task 13 owns; Task 2 owns the shell. Left intact deliberately rather than
   deleted on a partial result.
   Selectors use the data-testid values verified in the browser against the
   pinned streamlit==1.50.0 DOM, not guessed class names. */
.st-key-tl_auth_card [data-testid="stWidgetLabel"],
.st-key-tl_auth_card [data-testid="stWidgetLabel"] p,
.st-key-tl_auth_card [data-testid="stExpander"] summary,
.st-key-tl_auth_card [data-testid="stExpanderDetails"] p {{
  color: {TL_CONTENT_PRIMARY};
}}
.st-key-tl_auth_card [data-testid="stCaptionContainer"],
.st-key-tl_auth_card [data-testid="stCaptionContainer"] p {{
  color: {TL_CONTENT_SECONDARY};
}}
.st-key-tl_auth_card [data-testid="stExpander"] details {{
  background: transparent;
  border-color: {TL_LINE_HAIRLINE};
}}
.st-key-tl_auth_card [data-testid="stExpander"] summary {{
  min-height: 44px;
  align-items: center;
}}
/* Text and password fields. 44px minimum so the controls are comfortable
   on touch; Streamlit's own default is 38px. */
.st-key-tl_auth_card [data-testid="stTextInputRootElement"] {{
  background: {TL_SURFACE_ELEVATED};
  border: 1px solid {TL_LINE_HAIRLINE};
  min-height: 44px;
}}
/* BaseWeb nests its own container inside the root element and paints it
   white. Styling the root alone leaves a white field on the dark card —
   verified in the browser, not assumed. */
.st-key-tl_auth_card [data-baseweb="base-input"] {{
  background: {TL_SURFACE_ELEVATED};
}}
.st-key-tl_auth_card [data-testid="stTextInputRootElement"] input {{
  color: {TL_CONTENT_PRIMARY};
  -webkit-text-fill-color: {TL_CONTENT_PRIMARY};
  caret-color: {TL_PRIMARY};
  background: transparent;
  min-height: 42px;
}}
.st-key-tl_auth_card [data-testid="stTextInputRootElement"] input::placeholder {{
  color: {TL_CONTENT_SECONDARY};
}}
/* Focus lands on the wrapper, not the bare input — the wrapper is what the
   user sees as the field. Bright teal reads 11.3:1 on this card. */
.st-key-tl_auth_card [data-testid="stTextInputRootElement"]:focus-within {{
  border-color: {TL_PRIMARY};
  outline: 2px solid {TL_PRIMARY};
  outline-offset: 1px;
}}
/* One ring, not two: the wrapper carries focus, so the inner input must
   not also draw the workspace's own focus outline. */
.st-key-tl_auth_card [data-testid="stTextInputRootElement"] input:focus-visible {{
  outline: none;
}}
.st-key-tl_auth_card [data-testid="stTextInputRootElement"] button {{
  background: transparent;
  border: none;
  color: {TL_CONTENT_SECONDARY};
  min-width: 44px;
  min-height: 44px;
  padding: 0;
  flex: 0 0 44px;
}}
.st-key-tl_auth_card [data-testid="stTextInputRootElement"] button:focus-visible {{
  outline: 2px solid {TL_PRIMARY};
  outline-offset: 2px;
}}
/* Sign in / Create account switch. Streamlit's light chrome renders the
   inactive half as a near-white pill on the dark card. */
.st-key-tl_auth_card [data-testid="stBaseButton-segmented_control"] {{
  background: transparent;
  color: {TL_CONTENT_SECONDARY};
  border-color: {TL_LINE_HAIRLINE};
  min-height: 44px;
}}
.st-key-tl_auth_card [data-testid="stBaseButton-segmented_controlActive"] {{
  background: {TL_SURFACE_ELEVATED};
  color: {TL_CONTENT_PRIMARY};
  border-color: {TL_PRIMARY};
  min-height: 44px;
}}
/* The card's single primary action. Bright teal is the action colour on a
   dark surface (deep teal is its light-surface counterpart); dark label on
   bright teal reads 11.3:1 against white-on-deep-teal's 5.1:1. */
.st-key-tl_auth_card [data-testid="stFormSubmitButton"] button {{
  background: {TL_PRIMARY};
  color: {TL_SURFACE_CANVAS};
  border: 1px solid {TL_PRIMARY};
  font-weight: 600;
  min-height: 44px;
}}
.st-key-tl_auth_card [data-testid="stFormSubmitButton"] button:focus-visible {{
  outline: 2px solid {TL_PRIMARY};
  outline-offset: 2px;
}}
/* Streamlit's markdown anchor rule outranks a bare class, so the back link
   rendered in the browser's default blue.
   inline-flex + min-height gives the link a 44px hit area without changing
   how it looks: the text keeps its size, colour and weight and is centred
   in the taller box. The base rule's 10px top margin is dropped because the
   box now supplies that space itself — growing downward rather than with a
   negative margin, which would put the hit area on top of the compliance
   copy above it. */
.st-key-tl_auth_card a.tl-auth-back {{
  display: inline-flex;
  align-items: center;
  min-height: 44px;
  margin-top: 0;
  color: {TL_CONTENT_SECONDARY};
  text-decoration: none;
}}
.st-key-tl_auth_card a.tl-auth-back:focus-visible {{
  outline: 2px solid {TL_PRIMARY};
  outline-offset: 2px;
}}
.tl-auth-brand {{ display: flex; align-items: center; gap: 10px; }}
.tl-auth-word {{ font-weight: 700; font-size: 1.05rem; color: {TL_CONTENT_PRIMARY};
  letter-spacing: -0.01em; }}
.tl-auth-word em {{ font-style: normal; color: {TL_PRIMARY}; }}
.tl-auth-title {{ font-size: 1.5rem; font-weight: 700; color: {TL_CONTENT_PRIMARY};
  letter-spacing: -0.02em; margin: 18px 0 4px; }}
.tl-auth-sub {{ color: {TL_CONTENT_SECONDARY}; font-size: 0.9rem; margin-bottom: 18px; }}
.tl-auth-err {{
  margin-top: 12px; padding: 10px 13px; border-radius: 9px;
  border: 1px solid {TL_DANGER}59; background: {TL_DANGER_DIM};
  color: {TL_CONTENT_PRIMARY}; font-size: 0.85rem; line-height: 1.45;
}}
.tl-auth-ok {{
  margin-top: 12px; padding: 10px 13px; border-radius: 9px;
  border: 1px solid {TL_PRIMARY}59; background: {TL_PRIMARY}1f;
  color: {TL_CONTENT_PRIMARY}; font-size: 0.85rem; line-height: 1.45;
}}
.tl-auth-note {{
  margin-top: 18px; padding-top: 14px; border-top: 1px solid {TL_LINE_HAIRLINE};
  color: {TL_CONTENT_SECONDARY}; font-size: 0.78rem; line-height: 1.5;
}}
.tl-auth-note b {{ color: {TL_CONTENT_PRIMARY}; font-weight: 600; }}
.tl-auth-back {{ display: inline-block; margin-top: 10px; color: {TL_CONTENT_SECONDARY};
  font-size: 0.78rem; text-decoration: none; }}
.tl-auth-back:hover {{ color: {TL_PRIMARY}; }}
@media (max-width: 640px) {{
  .st-key-tl_auth_card,
  .tl-auth-card {{
    margin: 2vh auto 0; padding: 24px 20px 18px;
    max-width: calc(100% - 32px);
  }}
}}
@media (prefers-reduced-motion: no-preference) {{
  .st-key-tl_auth_card,
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
    from src.tradelens.ui.components.auth import _read_secret

    # The live marketing domain. This is a separate setting from the site's
    # own SITE_ORIGIN in vercel.json — changing one does not change the
    # other, so both were updated when the domain was pointed here.
    site_url = _read_secret(
        "TRADELENS_SITE_URL",
        "https://www.tradelensai.io",
    )
    return (
        '<div class="tl-auth-note"><b>Reflection only.</b> TradeLens reviews the '
        "trade you already took. It does not generate signals, predictions, or "
        "trade advice."
        f'<br><a class="tl-auth-back" href="{escape(site_url)}">'
        "&larr; Back to TradeLens AI</a></div>"
    )


_MODE_KEY = "_auth_mode"  # "login" | "signup"
_ERROR_KEY = "_login_error"
_SIGNUP_ERR = "_signup_error"
_RESET_MSG = "_reset_message"
_RESET_OK = "_reset_ok"
_RESET_DONE = "_reset_done"
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


def _render_reset_panel() -> None:
    """Request a reset code, then use it to set a new password.

    Both steps live on one panel because the trader leaves to read their
    inbox and comes back: hiding the second step behind a flow they have
    already navigated away from just adds a wrong turn.
    """
    import streamlit as st

    from src.tradelens.services.password_reset import complete_reset, request_reset

    st.caption(
        "We'll email a code to the address on your account. If you never "
        "added one, the account cannot be recovered — contact support."
    )

    with st.form("tl_reset_request", clear_on_submit=False):
        email = st.text_input("Email address", key="reset_email")
        asked = st.form_submit_button("Email me a code", width="stretch")
    if asked:
        outcome = request_reset(email)
        # Deliberately the same wording whether or not the address is
        # registered — see password_reset.request_reset.
        st.session_state[_RESET_MSG] = outcome.message
        st.session_state[_RESET_OK] = outcome.accepted

    if st.session_state.get(_RESET_MSG):
        renderer = _ok_html if st.session_state.get(_RESET_OK) else _error_html
        st.markdown(renderer(st.session_state[_RESET_MSG]), unsafe_allow_html=True)

    st.markdown(
        '<div class="tl-auth-sub">Already have a code?</div>',
        unsafe_allow_html=True,
    )
    with st.form("tl_reset_complete", clear_on_submit=False):
        code = st.text_input("Reset code", key="reset_code")
        new_password = st.text_input(
            "New password", type="password", key="reset_new_password"
        )
        applied = st.form_submit_button("Set new password", width="stretch")
    if applied:
        try:
            changed = complete_reset(code.strip(), new_password)
        except ValueError as exc:
            st.markdown(_error_html(str(exc)), unsafe_allow_html=True)
        else:
            if changed:
                st.session_state.pop(_RESET_MSG, None)
                st.session_state[_RESET_DONE] = True
                st.rerun()
            else:
                st.markdown(
                    _error_html(
                        "That code is not valid or has expired. Request a new "
                        "one above."
                    ),
                    unsafe_allow_html=True,
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
            if st.session_state.pop(_RESET_DONE, False):
                st.markdown(
                    _ok_html("Password updated. Sign in with your new password."),
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
            # An expander rather than a mode switch: swapping the card's
            # contents would remove the account toggle mid-session, and a
            # trader who mistyped their password should not lose the form
            # they were looking at to go and read their inbox.
            with st.expander("Forgot your password?"):
                _render_reset_panel()

        st.markdown(compliance_html(), unsafe_allow_html=True)
