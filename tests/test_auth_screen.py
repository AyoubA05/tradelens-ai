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
