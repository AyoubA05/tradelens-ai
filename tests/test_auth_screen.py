"""SP3 auth screen — presentation split out of auth.py."""


def test_auth_backdrop_asset_exists_and_is_small():
    from pathlib import Path

    p = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "tradelens"
        / "ui"
        / "assets"
        / "auth_bg.webp"
    )
    assert p.is_file(), "auth_bg.webp missing from ui/assets"
    # Reused marketing poster (~17KB). Guard against someone swapping in the
    # 4.8MB hero_bg.png by mistake.
    assert p.stat().st_size < 200_000, f"auth backdrop too large: {p.stat().st_size}"


def test_auth_css_is_scoped_and_tokenised():
    from src.tradelens.ui import design_system as ds
    from src.tradelens.ui.components import auth_screen

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


def test_render_auth_screen_exists_and_is_callable():
    from src.tradelens.ui.components import auth_screen

    assert callable(auth_screen.render_auth_screen)


def test_auth_screen_boots_in_apptest(tmp_path):
    """The screen renders without raising, and shows the compliance line."""
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


def test_successful_login_sets_session_keys(tmp_path, monkeypatch):
    """Regression: authenticate_login returns (ok, uname, uid) — the screen must
    unpack it and set the session keys, or every login loops back to the card."""
    from streamlit.testing.v1 import AppTest

    from src.tradelens.services import users
    from src.tradelens.ui.components import auth as auth_mod

    monkeypatch.setattr(users, "users_exist", lambda: False)  # secrets fallback
    # Pin the fallback credentials: earlier tests may leak TRADELENS_* env vars.
    monkeypatch.setenv("TRADELENS_USERNAME", "demo")
    monkeypatch.setenv("TRADELENS_PASSWORD", "tradelens2025")
    # signup toggle off: AppTest in streamlit 1.50 cannot serialize
    # st.segmented_control state on rerun (ValueError char-iteration bug);
    # the toggle is exercised visually in the Task 6 pass instead.
    monkeypatch.setattr(auth_mod, "signup_enabled", lambda: False)

    app = tmp_path / "auth_login_app.py"
    app.write_text(
        "import sys; sys.path.insert(0, '.')\n"
        "from src.tradelens.ui.components.auth_screen import render_auth_screen\n"
        "render_auth_screen()\n",
        encoding="utf-8",
    )
    at = AppTest.from_file(str(app), default_timeout=30).run()
    assert not at.exception
    # Fill the login form with the documented demo fallback and submit.
    at.text_input(key="login_username").set_value("demo")
    at.text_input(key="login_password").set_value("tradelens2025")
    at.button[0].set_value(True).run()
    assert not at.exception
    assert at.session_state["authenticated"] is True
    assert at.session_state["current_user"] == "demo"


def test_failed_login_shows_recovery_error(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    from src.tradelens.services import users
    from src.tradelens.ui.components import auth as auth_mod

    monkeypatch.setattr(users, "users_exist", lambda: False)
    monkeypatch.setattr(auth_mod, "signup_enabled", lambda: False)
    monkeypatch.setenv("TRADELENS_USERNAME", "demo")
    monkeypatch.setenv("TRADELENS_PASSWORD", "tradelens2025")

    app = tmp_path / "auth_fail_app.py"
    app.write_text(
        "import sys; sys.path.insert(0, '.')\n"
        "from src.tradelens.ui.components.auth_screen import render_auth_screen\n"
        "render_auth_screen()\n",
        encoding="utf-8",
    )
    at = AppTest.from_file(str(app), default_timeout=30).run()
    at.text_input(key="login_username").set_value("demo")
    at.text_input(key="login_password").set_value("wrong-password")
    at.button[0].set_value(True).run()
    assert not at.exception
    try:
        authed = at.session_state["authenticated"]
    except KeyError:
        authed = False
    assert authed is not True
    rendered = " ".join(m.value for m in at.markdown)
    assert "Check your details and try again" in rendered


def test_no_hardcoded_palette_in_auth_css():
    """Colors come from design_system tokens so the card can never drift."""
    import re

    from src.tradelens.ui import design_system as ds
    from src.tradelens.ui.components import auth_screen

    css = re.sub(r"/\*.*?\*/", "", auth_screen.auth_css(), flags=re.S)
    assert ds.TL_PRIMARY in css
    # The legacy landing palette must not reappear.
    assert "#20808D" not in css
    assert "#A84B2F" not in css
    # Any 6-digit hex present must be a known design-system token.
    known = {
        ds.TL_PRIMARY.lower(),
        ds.TL_SURFACE_CANVAS.lower(),
        ds.TL_SURFACE_PANEL.lower(),
        ds.TL_SURFACE_ELEVATED.lower(),
        ds.TL_LINE_HAIRLINE.lower(),
        ds.TL_CONTENT_PRIMARY.lower(),
        ds.TL_CONTENT_SECONDARY.lower(),
        ds.TL_DANGER.lower(),
    }
    for hexval in re.findall(r"#[0-9a-fA-F]{6}", css):
        assert hexval.lower() in known, f"untokenised color {hexval} in auth CSS"


def test_native_widgets_are_restyled_for_the_dark_card():
    """The card is the one dark surface in a light product.

    With the workspace base light, Streamlit paints labels, expander
    summaries and captions in ink and text inputs on white — on this card
    the labels came out invisible against their own background. Every fix
    must stay scoped to the card so widgets elsewhere keep framework chrome.
    """
    from src.tradelens.ui.components import auth_screen

    css = auth_screen.auth_css()
    for testid in (
        "stWidgetLabel",
        "stTextInputRootElement",
        "stFormSubmitButton",
        "stBaseButton-segmented_control",
        "stExpander",
        "stCaptionContainer",
    ):
        assert f'[data-testid="{testid}"]' in css, f"{testid} left unstyled"

    # BaseWeb nests its own white container inside the input root; styling
    # only the root leaves a white field on the dark card.
    assert '[data-baseweb="base-input"]' in css

    # Nothing may restyle a widget globally: every widget rule is a
    # descendant of the auth card container.
    #
    # Comments are stripped first. The scan reads raw lines, so a COMMENT that
    # merely quotes a selector — explaining which app-wide rule a scoped one
    # overrides, which is exactly the sort of thing worth writing down — was
    # reported as an unscoped rule leaking into the app. The property being
    # guarded is about selectors, so the input has to be selectors.
    import re as _re

    selectors_only = _re.sub(r"/\*.*?\*/", "", css, flags=_re.S)
    for line in selectors_only.splitlines():
        stripped = line.strip()
        if 'data-testid="st' in stripped and "stMainBlockContainer" not in stripped:
            assert stripped.startswith(
                (".st-key-tl_auth_card", ".tl-auth")
            ), f"unscoped widget rule leaks into the app: {stripped}"


def _css_declarations(css: str, selector: str) -> str:
    """Collect declarations from every flat CSS rule whose selector list
    contains `selector` exactly.

    Comments are stripped first: the selector-capturing pattern is greedy
    between braces, so a `/* ... */` block sitting above a rule is otherwise
    swallowed into that rule's selector text and the exact match silently
    fails — which reports a styled control as unstyled.
    """
    import re

    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    declarations = []
    for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        if selector in {candidate.strip() for candidate in selectors.split(",")}:
            declarations.append(body)
    return "\n".join(declarations)


def test_password_visibility_control_meets_the_touch_target_minimum():
    """Measured at 375px before the fix: 36x42. The reveal button sits in a
    flex row beside the input, so a minimum alone is not enough — flex would
    shrink it straight back below 44px as the field narrows."""
    from src.tradelens.ui.components import auth_screen

    css = auth_screen.auth_css()
    declarations = _css_declarations(
        css,
        '.st-key-tl_auth_card [data-testid="stTextInputRootElement"] button',
    )
    assert "min-width: 44px" in declarations
    assert "min-height: 44px" in declarations
    assert "flex: 0 0 44px" in declarations, "flex would shrink it back"


def test_password_field_wrapper_is_the_44px_hit_target():
    """The inner <input> is 42px because the wrapper carries a 1px border;
    the wrapper is what the user sees and clicks, so that is what must hold
    the minimum."""
    from src.tradelens.ui.components import auth_screen

    css = auth_screen.auth_css()
    declarations = _css_declarations(
        css,
        '.st-key-tl_auth_card [data-testid="stTextInputRootElement"]',
    )
    assert "min-height: 44px" in declarations


def test_back_to_website_link_meets_the_touch_target_minimum():
    """Measured at 375px and 1440px before the fix: 118x19.

    A text link still has to be tappable. inline-flex + a minimum height
    grows the hit area around the same text rather than restyling it, so
    the link's appearance is unchanged.
    """
    from src.tradelens.ui.components import auth_screen

    css = auth_screen.auth_css()
    declarations = _css_declarations(css, ".st-key-tl_auth_card a.tl-auth-back")
    assert "min-height: 44px" in declarations
    assert "display: inline-flex" in declarations
    assert "align-items: center" in declarations, "text must stay centred"
    # appearance is preserved: the rule must not resize or re-weight the text
    for restyle in ("font-size", "font-weight", "text-transform"):
        assert restyle not in declarations, f"{restyle} changes how the link looks"


def test_auth_recovery_summary_meets_the_touch_target_minimum():
    from src.tradelens.ui.components import auth_screen

    css = auth_screen.auth_css()
    declarations = _css_declarations(
        css,
        '.st-key-tl_auth_card [data-testid="stExpander"] summary',
    )
    assert "min-height: 44px" in declarations
    assert "align-items: center" in declarations


def test_auth_card_focus_is_visible_on_every_interactive_control():
    from src.tradelens.ui.components import auth_screen

    css = auth_screen.auth_css()
    assert ":focus-within" in css, "the field wrapper must show focus"
    assert css.count(":focus-visible") >= 3


def test_auth_card_text_meets_wcag_aa_on_its_own_surface():
    """Measured against the card, not the page behind it."""
    from src.tradelens.ui import design_system as ds

    from tests.test_design_system import contrast_ratio

    pairs = [
        ("label", ds.TL_CONTENT_PRIMARY, ds.TL_SURFACE_PANEL),
        ("caption", ds.TL_CONTENT_SECONDARY, ds.TL_SURFACE_PANEL),
        ("field text", ds.TL_CONTENT_PRIMARY, ds.TL_SURFACE_ELEVATED),
        ("placeholder", ds.TL_CONTENT_SECONDARY, ds.TL_SURFACE_ELEVATED),
        ("submit label", ds.TL_SURFACE_CANVAS, ds.TL_PRIMARY),
        ("focus ring", ds.TL_PRIMARY, ds.TL_SURFACE_PANEL),
    ]
    for name, fg, bg in pairs:
        ratio = contrast_ratio(fg, bg)
        assert ratio >= 4.5, f"auth {name} is {ratio:.2f}:1"


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


# ---------------------------------------------------------------------------
# Task 13 — credential fields a password manager can actually fill.
# ---------------------------------------------------------------------------

_SCREEN = None


def _screen_src() -> str:
    from pathlib import Path

    return (
        Path(__file__).resolve().parents[1]
        / "src/tradelens/ui/components/auth_screen.py"
    ).read_text(encoding="utf-8")


def test_every_credential_field_declares_its_autocomplete_purpose():
    """Spec §6.1 asks for autocomplete on the sign-in fields, and the screen
    carried it on none of them — zero occurrences across sign in, create
    account and reset.

    Worth stating why this is a real defect and not a framework limitation
    like `aria-sort`: `st.text_input` on the pinned streamlit==1.50.0 takes an
    `autocomplete` argument, checked against the installed signature before
    this was written. Without it a password manager cannot reliably offer a
    saved credential, and the browser may offer to save a *new* password over
    an existing one on the sign-in form.

    The purposes are the ones the HTML spec defines, and they differ per form:
    `current-password` on sign in, `new-password` where a password is being
    set, so a manager suggests a strong password in one place and fills the
    saved one in the other.
    """
    import ast

    src = _screen_src()
    tree = ast.parse(src)

    found = {}
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "text_input"
        ):
            continue
        kw = {
            k.arg: (k.value.value if isinstance(k.value, ast.Constant) else None)
            for k in node.keywords
        }
        key = kw.get("key")
        if key:
            found[key] = kw.get("autocomplete")

    expected = {
        "login_username": "username",
        "login_password": "current-password",
        "signup_username": "username",
        "signup_password": "new-password",
        "signup_confirm": "new-password",
        "reset_email": "email",
        "reset_new_password": "new-password",
    }
    for key, purpose in expected.items():
        assert key in found, f"{key} is gone — update this contract with it"
        assert (
            found[key] == purpose
        ), f"{key} declares autocomplete={found[key]!r}, expected {purpose!r}"


def test_the_invite_code_is_not_offered_a_saved_credential():
    """Not every field wants a purpose. The invite code is a one-off token,
    so leaving it unset is correct rather than an omission."""
    import ast

    for node in ast.walk(ast.parse(_screen_src())):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "text_input"
        ):
            kw = {
                k.arg: (k.value.value if isinstance(k.value, ast.Constant) else None)
                for k in node.keywords
            }
            if kw.get("key") == "signup_invite":
                assert "autocomplete" not in kw
