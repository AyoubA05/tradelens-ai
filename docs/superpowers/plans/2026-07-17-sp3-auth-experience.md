# SP3 Premium Auth Experience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the in-Streamlit duplicate landing page with a focused, premium auth card, and split `auth.py` into logic (`auth.py`) and presentation (`auth_screen.py`), per the approved spec (`docs/superpowers/specs/2026-07-17-sp3-auth-experience-design.md`).

**Architecture:** `auth.py` keeps all logic and stays the public entry point; a new `auth_screen.py` owns every pixel. `require_auth()` lazily imports `auth_screen.render_auth_screen()` inside the function body — the pattern `sidebar.py` already uses — which breaks the circular import (auth_screen imports logic from auth.py). The card renders over the marketing site's `poster-hero.webp`, reusing existing design-system tokens.

**Tech Stack:** Streamlit 1.50 (`st.segmented_control`, `st.form`, `st.spinner`), existing `design_system.py` tokens and `get_asset_as_base64`, pytest + Streamlit `AppTest`.

## Global Constraints

- **Never change auth logic.** Tokens, bcrypt, `authenticate_login`, `validate_signup`, `process_signup` keep identical behaviour and signatures. This is a presentation project.
- **Compliance copy is verbatim and must survive:** `"Reflection only."` + `"TradeLens reviews the trade you already took. It does not generate signals, predictions, or trade advice."`
- Design tokens only — import from `design_system.py` (`TL_PRIMARY`, `TL_BG`, `TL_SURFACE`, `TL_BORDER`, `TL_TEXT`, `TL_TEXT_MUTED`). No hardcoded hex in new code.
- **NO streamlit imports at module scope in `services/` or `db/`** (CLAUDE.md). `auth_screen.py` is a UI component so it may import streamlit, but keep Streamlit imports inside functions to match `auth.py`'s existing style.
- Scoped CSS only — every selector prefixed `.tl-auth-*`. Never style bare tags (breaks Streamlit widgets).
- No emoji as icons (SVG only). No side-tab accent borders. No gradient text.
- All motion gated behind `@media (prefers-reduced-motion: no-preference)`.
- Easing token: `cubic-bezier(0.16, 1, 0.3, 1)`. Micro-interactions 150–300ms.
- Commit after every task; stage paths explicitly (never `git add -A` — the tree carries unrelated dirty files).
- Branch off `main` (SP2 is merged at `e40bb35`).
- Default suite must stay green: currently **873 passed, 2 skipped**.

---

### Task 1: Copy the backdrop asset into the app

**Files:**
- Create: `src/tradelens/ui/assets/auth_bg.webp` (copied from `site/assets/poster-hero.webp`)
- Test: `tests/test_auth_screen.py`

**Interfaces:**
- Produces: `auth_bg.webp` readable by `get_asset_as_base64("auth_bg.webp")` (that helper reads `src/tradelens/ui/assets/<filename>` and returns `""` if missing).

- [x] **Step 1: Write the failing test** — create `tests/test_auth_screen.py`:

```python
"""SP3 auth screen — presentation split out of auth.py."""


def test_auth_backdrop_asset_exists_and_is_small():
    from pathlib import Path

    p = (
        Path(__file__).resolve().parents[1]
        / "src" / "tradelens" / "ui" / "assets" / "auth_bg.webp"
    )
    assert p.is_file(), "auth_bg.webp missing from ui/assets"
    # Reused marketing poster (~17KB). Guard against someone swapping in the
    # 4.8MB hero_bg.png by mistake.
    assert p.stat().st_size < 200_000, f"auth backdrop too large: {p.stat().st_size} bytes"
```

- [x] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_auth_screen.py -q`
Expected: FAIL with `AssertionError: auth_bg.webp missing from ui/assets`

- [x] **Step 3: Copy the asset**

```bash
cp site/assets/poster-hero.webp src/tradelens/ui/assets/auth_bg.webp
ls -la src/tradelens/ui/assets/auth_bg.webp
```
Expected: file exists, ~17 KB.

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_auth_screen.py -q`
Expected: PASS (1 passed).

- [x] **Step 5: Commit**

```bash
git add src/tradelens/ui/assets/auth_bg.webp tests/test_auth_screen.py
git commit -m "auth: add focused-card backdrop (reuses marketing hero poster, 17KB)"
```

### Task 2: Create `auth_screen.py` with the card CSS and markup

**Files:**
- Create: `src/tradelens/ui/components/auth_screen.py`
- Modify: `tests/test_auth_screen.py`

**Interfaces:**
- Consumes: `get_asset_as_base64(filename: str) -> str` from `design_system.py`; tokens `TL_PRIMARY`, `TL_BG`, `TL_SURFACE`, `TL_BORDER`, `TL_TEXT`, `TL_TEXT_MUTED` from `design_system.py`.
- Produces: `auth_css() -> str` (a `<style>` block), `brand_html(logo_b64: str = "") -> str`, `compliance_html() -> str`, and `render_auth_screen() -> None` (defined in Task 3; this task builds the pure-string helpers only).

- [x] **Step 1: Write the failing tests** — append to `tests/test_auth_screen.py`:

```python
def test_auth_css_is_scoped_and_tokenised():
    from src.tradelens.ui.components import auth_screen
    from src.tradelens.ui import design_system as ds

    css = auth_screen.auth_css()
    # Scoped: every rule targets .tl-auth-* (never bare tags — that breaks widgets).
    assert ".tl-auth-card" in css
    # Tokens, not hardcoded hex.
    assert ds.TL_PRIMARY in css
    # Anti-pattern guards carried over from the old landing tests.
    assert "border-left: 2px solid" not in css, "no side-tab accent borders"
    assert "background-clip: text" not in css, "no gradient text"
    assert "prefers-reduced-motion" in css, "motion must be gated"


def test_compliance_line_survives_verbatim():
    from src.tradelens.ui.components import auth_screen

    html = auth_screen.compliance_html()
    assert "Reflection only." in html
    assert "does not generate signals, predictions, or trade advice" in html


def test_brand_uses_svg_not_emoji():
    from src.tradelens.ui.components import auth_screen

    html = auth_screen.brand_html()
    assert "<svg" in html
    for emoji in ("📈", "🎯", "🚀", "✨"):
        assert emoji not in html
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_auth_screen.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.tradelens.ui.components.auth_screen'`

- [x] **Step 3: Create `src/tradelens/ui/components/auth_screen.py`**

```python
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
     TL_BG #0d0f11. Mixing the two is exactly the drift SP3 removes. */
  background: linear-gradient(180deg, {TL_BG}d1, {TL_BG} 92%);
}}
.tl-auth-card {{
  position: relative; z-index: 1;
  max-width: 420px; margin: 6vh auto 0;
  background: {TL_SURFACE};
  border: 1px solid {TL_BORDER};
  border-radius: 16px;
  padding: 30px 30px 22px;
  box-shadow: 0 24px 60px rgba(0,0,0,0.55);
}}
.tl-auth-brand {{ display: flex; align-items: center; gap: 10px; }}
.tl-auth-word {{ font-weight: 700; font-size: 1.05rem; color: {TL_TEXT}; letter-spacing: -0.01em; }}
.tl-auth-word em {{ font-style: normal; color: {TL_PRIMARY}; }}
.tl-auth-title {{ font-size: 1.5rem; font-weight: 700; color: {TL_TEXT};
  letter-spacing: -0.02em; margin: 18px 0 4px; }}
.tl-auth-sub {{ color: {TL_TEXT_MUTED}; font-size: 0.9rem; margin-bottom: 18px; }}
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
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_auth_screen.py -q`
Expected: PASS (4 passed).

- [x] **Step 5: Lint**

Run: `ruff check src/tradelens/ui/components/auth_screen.py tests/test_auth_screen.py && black --check src/tradelens/ui/components/auth_screen.py tests/test_auth_screen.py`
Expected: `All checks passed!` and `2 files would be left unchanged.`

- [x] **Step 6: Commit**

```bash
git add src/tradelens/ui/components/auth_screen.py tests/test_auth_screen.py
git commit -m "auth: auth_screen.py — scoped card CSS, brand lockup, compliance note"
```

### Task 3: Render the card (toggle, forms, errors, submit feedback)

**Files:**
- Modify: `src/tradelens/ui/components/auth_screen.py`
- Modify: `tests/test_auth_screen.py`

**Interfaces:**
- Consumes (from `auth.py`, imported lazily inside the function to avoid the circular import): `authenticate_login(username, password)`, `process_signup(username, password, confirm, invite) -> str | None`, `signup_enabled() -> bool`, `_persist_token(st)`.
- Produces: `render_auth_screen() -> None` — renders the whole screen and calls `st.stop()`-free (the caller `require_auth()` owns halting).

- [x] **Step 1: Write the failing test** — append to `tests/test_auth_screen.py`:

```python
def test_render_auth_screen_exists_and_is_callable():
    from src.tradelens.ui.components import auth_screen

    assert callable(auth_screen.render_auth_screen)


def test_auth_screen_boots_in_apptest(tmp_path):
    """The screen renders without raising, and shows the sign-in affordance."""
    from streamlit.testing.v1 import AppTest

    app = tmp_path / "auth_app.py"
    app.write_text(
        "import sys; sys.path.insert(0, '.')\n"
        "from src.tradelens.ui.components.auth_screen import render_auth_screen\n"
        "render_auth_screen()\n",
        encoding="utf-8",
    )
    at = AppTest.from_file(str(app), default_timeout=30).run()
    assert not at.exception
    rendered = " ".join(m.value for m in at.markdown)
    assert "Reflection only." in rendered
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_auth_screen.py -q`
Expected: FAIL with `AttributeError: module ... has no attribute 'render_auth_screen'`

- [x] **Step 3: Implement** — append to `src/tradelens/ui/components/auth_screen.py`:

```python
_MODE_KEY = "_auth_mode"  # "login" | "signup"
_ERROR_KEY = "_login_error"
_SIGNUP_ERR = "_signup_error"


def _error_html(message: str) -> str:
    """Error region. aria-live so screen readers announce it (WCAG)."""
    return (
        '<div class="tl-auth-err" role="alert" aria-live="polite">'
        f"{escape(message)}</div>"
    )


def render_auth_screen() -> None:
    """Render the focused auth card. Logic stays in auth.py."""
    import streamlit as st

    from src.tradelens.ui.components.auth import (
        authenticate_login,
        process_signup,
        signup_enabled,
    )

    st.markdown(auth_css(), unsafe_allow_html=True)
    st.markdown('<div class="tl-auth-bg"></div>', unsafe_allow_html=True)
    st.markdown('<div class="tl-auth-scrim"></div>', unsafe_allow_html=True)

    with st.container(key="tl_auth_card"):
        st.markdown(brand_html(get_asset_as_base64("logo_mark.png")), unsafe_allow_html=True)

        can_signup = signup_enabled()
        mode = st.session_state.get(_MODE_KEY, "login")
        if can_signup:
            choice = st.segmented_control(
                "Account",
                options=["Sign in", "Create account"],
                default="Create account" if mode == "signup" else "Sign in",
                key="tl_auth_mode_toggle",
                label_visibility="collapsed",
            )
            mode = "signup" if choice == "Create account" else "login"
            st.session_state[_MODE_KEY] = mode

        if mode == "signup":
            st.markdown(
                '<div class="tl-auth-title">Create your account</div>'
                '<div class="tl-auth-sub">An invite code is required during beta.</div>',
                unsafe_allow_html=True,
            )
            with st.form("tl_signup", clear_on_submit=False):
                username = st.text_input("Username", key="signup_username")
                password = st.text_input("Password", type="password", key="signup_password")
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
                    st.session_state.pop(_SIGNUP_ERR, None)
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
            with st.form("tl_login", clear_on_submit=False):
                username = st.text_input("Username", key="login_username")
                password = st.text_input("Password", type="password", key="login_password")
                submitted = st.form_submit_button("Sign in", width="stretch")
            if submitted:
                with st.spinner("Signing you in…"):
                    try:
                        ok = authenticate_login(username, password)
                    except Exception:  # noqa: BLE001 — never crash the login screen
                        ok = False
                if ok:
                    st.session_state.pop(_ERROR_KEY, None)
                    st.rerun()
                else:
                    st.session_state[_ERROR_KEY] = (
                        "Incorrect username or password. Check your details and try again."
                    )
            if st.session_state.get(_ERROR_KEY):
                st.markdown(
                    _error_html(st.session_state[_ERROR_KEY]), unsafe_allow_html=True
                )

        st.markdown(compliance_html(), unsafe_allow_html=True)
```

Then add the error style to `auth_css()`'s `<style>` block, immediately before the `@media (max-width: 640px)` rule:

```css
.tl-auth-err {{
  margin-top: 12px; padding: 10px 13px; border-radius: 9px;
  border: 1px solid {TL_DANGER}59; background: {TL_DANGER_DIM};
  color: {TL_TEXT}; font-size: 0.85rem; line-height: 1.45;
}}
@media (prefers-reduced-motion: no-preference) {{
  .tl-auth-err {{ animation: tl-auth-fade 200ms {_EASE} both; }}
  @keyframes tl-auth-fade {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
}}
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_auth_screen.py -q`
Expected: PASS (6 passed).

- [x] **Step 5: Commit**

```bash
git add src/tradelens/ui/components/auth_screen.py tests/test_auth_screen.py
git commit -m "auth: focused card render — segmented toggle, forms, aria-live errors, submit spinner"
```

### Task 4: Strip presentation from `auth.py` and wire `require_auth`

**Files:**
- Modify: `src/tradelens/ui/components/auth.py`

**Interfaces:**
- Consumes: `auth_screen.render_auth_screen()` (Task 3).
- Produces: `auth.py` with logic only; `require_auth()` unchanged in signature and public behaviour.

- [x] **Step 1: Delete the presentation block.** Remove these definitions from `src/tradelens/ui/components/auth.py` entirely: `_IC_SHOT`, `_IC_CHART`, `_IC_REVIEW`, `_EQUITY_SVG`, `_landing_css`, `_landing_header_html`, `_landing_hero_html`, `_landing_features_html`, `_landing_footer_html`, `_render_hero_visual`, `_render_login`, `_render_login_form`, `_render_signup_form`. Also drop the now-unused imports they needed (`BORDER`, `HEADING_FONT`, `MONO_FONT`, `SURFACE`, `TEXT_MUTED`, `TEXT_PRIMARY`, `TEXT_SECONDARY`, `TL_PRIMARY`, `TL_PRIMARY_DIM`) — keep any that remaining logic still uses.

- [x] **Step 2: Point `require_auth` at the new screen.** Replace the body of `require_auth()` with:

```python
def require_auth() -> None:
    """Gate every page: restore a session, else render the auth screen and halt."""
    import streamlit as st

    _try_restore(st)

    if is_authenticated():
        _persist_token(st)
        return

    # Lazy import: auth_screen imports logic from this module, so a top-level
    # import here would be circular (same pattern sidebar.py uses).
    from src.tradelens.ui.components.auth_screen import render_auth_screen

    render_auth_screen()
    st.stop()
```

- [x] **Step 3: Verify no dead references remain**

```bash
grep -nE "_landing_|_render_login|_render_hero_visual|_IC_SHOT|_EQUITY_SVG" src/ tests/ || echo "clean"
```
Expected: only hits inside `tests/test_landing_login.py` (rewritten in Task 5). No hits in `src/`.

- [x] **Step 4: Confirm the file shrank and still imports**

```bash
wc -l src/tradelens/ui/components/auth.py
python -c "from src.tradelens.ui.components import auth; print('ok', callable(auth.require_auth))"
```
Expected: well under 450 lines; prints `ok True`.

- [x] **Step 5: Lint**

Run: `ruff check src/tradelens/ui/components/auth.py && black --check src/tradelens/ui/components/auth.py`
Expected: `All checks passed!` (ruff will catch any import left unused by the deletions).

- [x] **Step 6: Commit**

```bash
git add src/tradelens/ui/components/auth.py
git commit -m "auth: strip duplicate landing page; auth.py is logic only, require_auth renders auth_screen"
```

### Task 5: Rewrite the landing/login test suite

**Files:**
- Delete: `tests/test_landing_login.py`
- Modify: `tests/test_auth_screen.py`

**Interfaces:**
- Consumes: `auth_screen.auth_css()`, `auth_screen.compliance_html()`, `auth_screen.brand_html()` (Task 2).

- [x] **Step 1: Port the assertions worth keeping.** Append to `tests/test_auth_screen.py`:

```python
def test_no_hardcoded_palette_in_auth_css():
    """Colors come from design_system tokens so the card can never drift."""
    import re

    from src.tradelens.ui.components import auth_screen
    from src.tradelens.ui import design_system as ds

    css = auth_screen.auth_css()
    assert ds.TL_PRIMARY in css
    # The legacy landing palette must not reappear.
    assert "#20808D" not in css
    assert "#A84B2F" not in css
    # Any 6-digit hex present must be a known design-system token.
    known = {
        ds.TL_PRIMARY.lower(), ds.TL_BG.lower(), ds.TL_SURFACE.lower(),
        ds.TL_BORDER.lower(), ds.TL_TEXT.lower(), ds.TL_TEXT_MUTED.lower(),
    }
    for hexval in re.findall(r"#[0-9a-fA-F]{6}", css):
        assert hexval.lower() in known, f"untokenised color {hexval} in auth CSS"


def test_auth_card_is_the_intentional_centered_exception():
    """The old landing page must not be centered; a focused auth card must be.

    Replaces test_no_centered_everything, which was written for the deleted
    landing layout and now conflicts with the approved SP3 design.
    """
    from src.tradelens.ui.components import auth_screen

    css = auth_screen.auth_css()
    assert "margin: 6vh auto 0" in css, "card should be horizontally centered"
    assert "max-width: 420px" in css, "card must stay focused, not full-bleed"


def test_scope_line_is_honest_no_signals():
    """Carried over from the old suite — compliance copy is load-bearing."""
    from src.tradelens.ui.components import auth_screen

    note = auth_screen.compliance_html().lower()
    assert "does not generate signals" in note
    assert "reflection only" in note
```

- [x] **Step 2: Delete the obsolete suite**

```bash
git rm tests/test_landing_login.py
```

- [x] **Step 3: Run the full suite**

Run: `DEMO_MODE=true pytest tests/ -q`
Expected: all green. Count math: 873 - 13 (deleted `test_landing_login.py`) + 9 (`test_auth_screen.py`) = **869 passed, 2 skipped**.

- [x] **Step 4: Confirm no test still references deleted functions**

```bash
grep -rnE "_landing_|_render_login" tests/ || echo "clean"
```
Expected: `clean`.

- [x] **Step 5: Commit**

```bash
git add tests/test_auth_screen.py
git rm --cached tests/test_landing_login.py 2>/dev/null || true
git commit -m "test: replace landing-login suite with auth_screen tests"
```

### Task 6: Visual verification and polish pass

**Files:**
- Modify: `src/tradelens/ui/components/auth_screen.py` (fixes only as found)

- [x] **Step 1: Boot the app logged out**

```bash
source .venv/bin/activate
TRADELENS_SESSION_SECRET=qa DEMO_MODE=true streamlit run src/tradelens/ui/app.py --server.headless true --server.port 8501
```
Open `http://localhost:8501` with no `?auth=` token so the auth screen renders.

- [x] **Step 2: Capture the screen at three widths** using the CDP driver (see `.claude/` memory `visual-qa-cdp-screenshots`; script at `<scratchpad>/cdp_shot.py`):

```bash
CDP_FULL=0 python <scratchpad>/cdp_shot.py "http://localhost:8501/?v=1" "<scratchpad>/shots/auth-1440.png" 1440 900 12
CDP_FULL=0 python <scratchpad>/cdp_shot.py "http://localhost:8501/?v=2" "<scratchpad>/shots/auth-768.png" 768 1024 12
CDP_FULL=0 python <scratchpad>/cdp_shot.py "http://localhost:8501/?v=3" "<scratchpad>/shots/auth-375.png" 375 812 12
```
Review each: card centered and focused at 420px on desktop, full-width with 16px gutters at 375, backdrop visible but not competing with the card, compliance note legible.

- [x] **Step 3: Reduced-motion check**

```bash
CDP_RM=1 CDP_FULL=0 python <scratchpad>/cdp_shot.py "http://localhost:8501/?v=4" "<scratchpad>/shots/auth-rm.png" 1280 800 12
```
Expected: card fully visible and static (no entrance animation mid-flight).

- [x] **Step 4: Exercise the error path.** In the browser, submit a wrong password. Confirm: spinner appears during the check, then a red-bordered message reading "Incorrect username or password. Check your details and try again." renders below the form, and the page does not crash.

- [x] **Step 5: Exercise the toggle.** Click "Create account" — the signup fields (username, password, confirm, invite code) replace the login fields, and clicking "Sign in" returns. Submit signup with mismatched passwords and confirm a specific error appears.

- [x] **Step 6: Final gates**

```bash
DEMO_MODE=true pytest tests/ -q          # expect 869 passed, 2 skipped
ruff check src/ scripts/                  # expect All checks passed!
black --check src/ scripts/               # expect unchanged
```

- [x] **Step 7: Commit any fixes and close the plan**

```bash
git add src/tradelens/ui/components/auth_screen.py docs/superpowers/plans/2026-07-17-sp3-auth-experience.md
git commit -m "auth: SP3 verification fixes — premium auth card complete"
```
