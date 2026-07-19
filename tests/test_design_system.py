"""
Tests for src/tradelens/ui/design_system.py (2026-07 UI polish, Phase 1).

Covers: token values match the PRODUCT.md palette, build_css() is pure /
deterministic / scoped-selector-only (mirrors the R1 rule from
test_theme.py), the module never imports Streamlit at module level, and
every render_* helper produces correct, escaped HTML for its component
states (positive/negative/missing KPI, insight variants, confidence
tiers, stepper done/active/future, missing-asset fallback).
"""

import re
from pathlib import Path

from src.tradelens.ui import design_system as ds

ROOT = Path(__file__).resolve().parents[1]

# Bare element tags the CSS must NEVER target unscoped (R1 mitigation).
_FORBIDDEN_BARE = {
    "p",
    "div",
    "span",
    "a",
    "button",
    "input",
    "select",
    "textarea",
    "body",
    "html",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "section",
    "ul",
    "ol",
    "li",
    "table",
    "tr",
    "td",
    "th",
    "img",
    "label",
    "form",
    "header",
    "main",
    "nav",
    "aside",
}


def _top_level_selectors(css: str) -> list[str]:
    """Extract each selector group (text before a `{`), dropping at-rules."""
    css = css.replace("<style>", "").replace("</style>", "")
    css = re.sub(r"@import\s+url\([^)]*\)\s*;", "", css)
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    groups = re.findall(r"([^{}]+)\{", css)
    out = []
    for g in groups:
        g = g.strip()
        if g and not g.startswith("@"):
            out.append(g)
    return out


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------


def test_palette_tokens_match_product_contract():
    # SP4: the app adopts the marketing site's palette (brand unification).
    # danger brightened from #ef4444 for WCAG AA on the lighter surfaces.
    assert ds.TL_BG == "#0d1117"
    assert ds.TL_SURFACE == "#161b22"
    assert ds.TL_PRIMARY == "#00e5cc"
    assert ds.TL_SUCCESS == "#22c55e"
    assert ds.TL_DANGER == "#f56565"
    assert ds.TL_WARNING == "#f59e0b"


def test_all_color_tokens_nonempty_strings():
    for name in dir(ds):
        if name.startswith("TL_") and not name.startswith("TL_FONT"):
            val = getattr(ds, name)
            assert isinstance(val, str) and val, f"{name} must be non-empty str"


def test_font_tokens_defined():
    assert "JetBrains Mono" in ds.TL_FONT_MONO
    assert "Inter" in ds.TL_FONT_BODY


def test_no_module_level_streamlit_import():
    """Module must stay Streamlit-free so services/tests can import it."""
    import sys

    src = Path(ds.__file__).read_text(encoding="utf-8")
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import streamlit", "from streamlit")):
            # allowed only inside a function body (indented)
            assert line != stripped, f"top-level streamlit import: {line!r}"
    # importing the module must not have pulled in streamlit as a side effect
    assert "src.tradelens.ui.design_system" in sys.modules


# ---------------------------------------------------------------------------
# CSS — determinism + scoped-selector rule (R1)
# ---------------------------------------------------------------------------


def test_build_css_returns_style_block():
    css = ds.build_css()
    assert isinstance(css, str)
    assert css.startswith("<style>") and css.endswith("</style>")


def test_build_css_is_deterministic():
    assert ds.build_css() == ds.build_css()


def test_css_uses_only_scoped_selectors():
    """R1: every selector chain starts with a scoped anchor, never a bare tag."""
    selectors = _top_level_selectors(ds.build_css())
    assert selectors, "expected at least one CSS rule"
    for group in selectors:
        for sel in group.split(","):
            sel = sel.strip()
            if not sel:
                continue
            first = re.split(r"[\s>+~]", sel)[0]
            assert first[0] in ".#[:", f"unscoped selector: {sel!r}"
            assert first.lower() not in _FORBIDDEN_BARE, f"bare tag: {sel!r}"


def test_css_uses_only_proven_testids():
    """Only the data-testid set proven in this repo on streamlit==1.50.0."""
    proven = {
        "stAppViewContainer",
        "stHeader",
        "stSidebar",
        "stMetricValue",
        "stMetricDelta",
        "stMetricLabel",
    }
    used = set(re.findall(r'data-testid="([^"]+)"', ds.build_css()))
    assert used <= proven, f"unproven testids: {used - proven}"


def test_css_has_no_colored_side_borders_on_insight_cards():
    """PRODUCT.md anti-pattern: no colored left/right borders on cards."""
    css = ds.build_css()
    assert "border-left" not in css
    assert "border-right: 1px solid var(--tl-border)" in css  # sidebar only
    assert css.count("border-right") == 1


def test_css_defines_reduced_motion_block():
    assert "prefers-reduced-motion" in ds.build_css()


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


def test_fmt_value_currency():
    assert ds._fmt_value(1234.5, "currency") == "$1,234.50"
    assert ds._fmt_value(-987.6, "currency") == "-$987.60"
    assert ds._fmt_value(0, "currency") == "$0.00"


def test_fmt_value_none_is_na():
    for fmt in ("currency", "percent", "number", "ratio"):
        assert ds._fmt_value(None, fmt) == "N/A"


def test_fmt_value_percent_number_ratio():
    assert ds._fmt_value(61.279, "percent") == "61.3%"
    assert ds._fmt_value(12345, "number") == "12,345"
    assert ds._fmt_value(2.25, "ratio") == "2.2x"


def test_fmt_value_ratio_infinity():
    assert ds._fmt_value(float("inf"), "ratio") == "∞"


def test_sign_class():
    assert ds._sign_class(5) == "positive"
    assert ds._sign_class(-5) == "negative"
    assert ds._sign_class(0) == ""
    assert ds._sign_class(None) == "missing"


# ---------------------------------------------------------------------------
# KPI card
# ---------------------------------------------------------------------------


def test_kpi_card_positive_currency():
    html = ds.render_kpi_card("Net P&L", 2800.0)
    assert "tl-kpi-card" in html
    assert "tl-kpi-value positive" in html
    assert "$2,800.00" in html
    assert "Net P&amp;L" in html  # label is escaped


def test_kpi_card_negative_and_delta():
    html = ds.render_kpi_card("Net P&L", -120.5, delta=-30.0)
    assert "tl-kpi-value negative" in html
    assert "-$120.50" in html
    assert "tl-kpi-delta negative" in html
    assert "▼" in html


def test_kpi_card_missing_value():
    html = ds.render_kpi_card("Avg R", None, format="ratio")
    assert "N/A" in html
    assert "missing" in html


def test_kpi_card_noncurrency_value_not_sign_colored():
    html = ds.render_kpi_card("Win rate", 61.0, format="percent")
    assert "tl-kpi-value positive" not in html
    assert "61.0%" in html


# ---------------------------------------------------------------------------
# Badges & confidence
# ---------------------------------------------------------------------------


def test_badge_variants():
    assert "tl-badge-success" in ds.render_badge("Win", "success")
    assert "tl-badge-primary" in ds.render_badge("A+", "primary")


def test_badge_unknown_variant_falls_back_to_neutral():
    assert "tl-badge-neutral" in ds.render_badge("x", "no-such-variant")


def test_badge_escapes_text():
    assert "&lt;b&gt;" in ds.render_badge("<b>", "neutral")


def test_confidence_tiers_and_no_red():
    high = ds.confidence_badge(0.70)
    med = ds.confidence_badge(0.40)
    low = ds.confidence_badge(0.39)
    assert "tl-confidence-high" in high and "70%" in high
    assert "tl-confidence-medium" in med
    assert "tl-confidence-low" in low
    # red is for errors only — never for confidence
    for html in (high, med, low):
        assert "danger" not in html


# ---------------------------------------------------------------------------
# Insight card
# ---------------------------------------------------------------------------


def test_insight_card_variants():
    html = ds.render_insight_card("↑", "Title", "Body", "3 trades", 0.8, "strength")
    assert 'class="tl-insight-card strength"' in html
    assert "tl-confidence-high" in html
    assert "Evidence: 3 trades" in html


def test_insight_card_unknown_variant_neutral():
    html = ds.render_insight_card("•", "T", "B", "E", 0.5, "bogus")
    assert 'class="tl-insight-card neutral"' in html


def test_insight_card_escapes_user_text():
    html = ds.render_insight_card("•", "<x>", "<y>", "<z>", 0.5)
    assert "<x>" not in html and "&lt;x&gt;" in html


# ---------------------------------------------------------------------------
# Empty state / banner / section header / chips
# ---------------------------------------------------------------------------


def test_empty_state_basic():
    html = ds.render_empty_state("📓", "No trades yet", "Log your first trade")
    assert "tl-empty-card" in html
    assert "No trades yet" in html
    assert "tl-empty-img" not in html  # no image requested


def test_empty_state_missing_asset_degrades():
    html = ds.render_empty_state("📓", "T", "B", image_path="nope.png")
    assert "tl-empty-img" not in html  # asset absent → no broken <img>


def test_empty_state_action_label():
    html = ds.render_empty_state("📓", "T", "B", action_label="Log a trade")
    assert "tl-empty-action" in html and "Log a trade" in html


def test_banner_variants_and_fallback():
    assert "tl-banner-info" in ds.render_banner("hi", "info")
    assert "tl-banner-warning" in ds.render_banner("hi", "bogus")


def test_section_header_with_and_without_subtitle():
    with_sub = ds.render_section_header("Today", "Mon 6 Jul")
    without = ds.render_section_header("Today")
    assert "tl-section-subtitle" in with_sub
    assert "tl-section-subtitle" not in without


def test_chip_row_color_map():
    html = ds.render_chip_row(["FVG", "OB"], {"FVG": "primary"})
    assert "tl-badge-primary" in html
    assert "tl-badge-neutral" in html
    assert html.startswith('<div class="tl-chip-row">')


# ---------------------------------------------------------------------------
# Step indicator
# ---------------------------------------------------------------------------


def test_stepper_states():
    html = ds.render_step_indicator(2, ["Setup", "Entry", "Review"])
    assert 'tl-step-circle done">✓' in html
    assert 'tl-step-circle active">2' in html
    assert 'tl-step-circle future">3' in html


def test_stepper_connectors():
    html = ds.render_step_indicator(2, ["A", "B", "C"])
    assert html.count("tl-step-connector") == 2
    assert "tl-step-connector done" in html
    assert "tl-step-connector future" in html


def test_stepper_first_step_no_done():
    html = ds.render_step_indicator(1, ["A", "B"])
    assert "✓" not in html


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------


def test_get_asset_as_base64_missing_returns_empty():
    assert ds.get_asset_as_base64("definitely_not_here.png") == ""


def test_get_asset_as_base64_reads_real_file(tmp_path, monkeypatch):
    asset = tmp_path / "tiny.png"
    asset.write_bytes(b"\x89PNG\r\n\x1a\n")
    monkeypatch.setattr(ds, "ASSETS_DIR", tmp_path)
    out = ds.get_asset_as_base64("tiny.png")
    assert out and isinstance(out, str)
    import base64

    assert base64.b64decode(out) == b"\x89PNG\r\n\x1a\n"


def test_app_palette_matches_marketing_site():
    """SP4 seam guard: the app and site must share one palette.

    Reads the CSS custom properties out of site/styles.css and compares them to
    the app tokens, so re-theming either surface without the other fails here
    instead of shipping a visible seam at the site -> app handoff.
    """
    import re
    from pathlib import Path

    css = (Path(__file__).resolve().parents[1] / "site" / "styles.css").read_text(
        encoding="utf-8"
    )

    def site_var(name: str) -> str:
        m = re.search(rf"--{name}:\s*(#[0-9a-fA-F]{{6}})", css)
        assert m, f"--{name} not found in site/styles.css"
        return m.group(1).lower()

    assert ds.TL_BG.lower() == site_var("bg")
    assert ds.TL_SURFACE.lower() == site_var("surface")
    assert ds.TL_SURFACE_2.lower() == site_var("surface-2")
    assert ds.TL_PRIMARY.lower() == site_var("accent")
