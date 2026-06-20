"""
Tests for the design-system theme module (Phase 1, week6-d1).

Covers: design tokens are defined, the Plotly template is a real Template,
inject_css() is deterministic and runs inside AppTest, charts.py pulls its
brand colors from theme (single source of truth), and — critically (R1) — the
injected CSS only ever uses SCOPED selectors, never bare HTML element tags.
"""

import re
from pathlib import Path

import plotly.graph_objects as go

from src.tradelens.ui.components import theme

ROOT = Path(__file__).resolve().parents[1]

# Bare element tags inject_css() must NEVER target unscoped (R1 mitigation).
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
    # strip whole @import url(...); — the font URL contains internal semicolons
    css = re.sub(r"@import\s+url\([^)]*\)\s*;", "", css)
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


def test_core_color_tokens_defined():
    for name in (
        "BG",
        "SURFACE",
        "BORDER",
        "TEAL",
        "TERRA",
        "TEXT_PRIMARY",
        "TEXT_SECONDARY",
        "TEXT_MUTED",
    ):
        val = getattr(theme, name)
        assert isinstance(val, str) and val, f"{name} must be a non-empty string"


def test_brand_colors_match_spec():
    assert theme.BG == "#0E1117"
    assert theme.TEAL == "#20808D"
    assert theme.TERRA == "#A84B2F"


def test_font_stacks_defined():
    assert theme.HEADING_FONT
    assert theme.MONO_FONT == "JetBrains Mono"


def test_grade_colors_span_teal_to_terra():
    assert theme.GRADE_COLORS["A+"] == theme.TEAL
    assert theme.GRADE_COLORS["F"] == theme.TERRA


def test_killzone_labels_present():
    assert theme.KILLZONE_LABELS["ny_am"] == "NY AM"


# ---------------------------------------------------------------------------
# Plotly template
# ---------------------------------------------------------------------------


def test_plotly_template_is_template_object():
    assert isinstance(theme.PLOTLY_TEMPLATE, go.layout.Template)


def test_plotly_template_is_transparent():
    layout = theme.PLOTLY_TEMPLATE.layout
    assert layout.paper_bgcolor == "rgba(0,0,0,0)"
    assert layout.plot_bgcolor == "rgba(0,0,0,0)"


# ---------------------------------------------------------------------------
# CSS — determinism + scoped-selector rule (R1)
# ---------------------------------------------------------------------------


def test_build_css_returns_nonempty_str():
    css = theme._build_css()
    assert isinstance(css, str) and "<style>" in css


def test_build_css_is_deterministic():
    assert theme._build_css() == theme._build_css()


def test_css_uses_only_scoped_selectors():
    """R1: every selector chain must start with a scoped anchor, never a bare tag."""
    selectors = _top_level_selectors(theme._build_css())
    assert selectors, "expected at least one CSS rule"
    for group in selectors:
        for sel in group.split(","):
            sel = sel.strip()
            if not sel:
                continue
            first = re.split(r"[\s>+~]", sel)[0]
            assert first[0] in ".#[:", f"unscoped selector: {sel!r}"
            assert first.lower() not in _FORBIDDEN_BARE, f"bare tag selector: {sel!r}"


def test_inject_css_runs_in_apptest():
    from streamlit.testing.v1 import AppTest

    script = (
        "import sys\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "from src.tradelens.ui.components.theme import inject_css\n"
        "inject_css()\n"
        "inject_css()\n"  # idempotent — calling twice must not error
    )
    at = AppTest.from_string(script).run()
    assert not at.exception


# ---------------------------------------------------------------------------
# charts.py single-source-of-truth
# ---------------------------------------------------------------------------


def test_charts_pull_brand_colors_from_theme():
    from src.tradelens.ui.components import charts

    assert charts._TEAL == theme.TEAL
    assert charts._RED == theme.TERRA
