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


def test_successful_login_sets_session_keys(tmp_path):
    """Regression: authenticate_login returns (ok, uname, uid) — the screen must
    unpack it and set the session keys, or every login loops back to the card."""
    from streamlit.testing.v1 import AppTest

    app = tmp_path / "auth_login_app.py"
    app.write_text(
        "import sys; sys.path.insert(0, '.')\n"
        "from src.tradelens.services import users\n"
        "users.users_exist = lambda: False  # hermetic: force secrets fallback\n"
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


def test_failed_login_shows_recovery_error(tmp_path):
    from streamlit.testing.v1 import AppTest

    app = tmp_path / "auth_fail_app.py"
    app.write_text(
        "import sys; sys.path.insert(0, '.')\n"
        "from src.tradelens.services import users\n"
        "users.users_exist = lambda: False\n"
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
