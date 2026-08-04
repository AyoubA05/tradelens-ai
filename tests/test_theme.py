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
    # strip /* ... */ comments so they never merge into the next selector
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
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


def test_brand_colors_collapse_to_design_system():
    """SP4: theme.py no longer defines a competing teal — it re-exports the
    design-system token, so the app has exactly one brand color."""
    from src.tradelens.ui import design_system as ds

    assert theme.TEAL == ds.TL_PRIMARY
    assert theme.TEAL_HOVER == ds.TL_PRIMARY_HOVER
    assert theme.TEAL_SOFT == ds.TL_PRIMARY_DIM
    # The legacy teal must be gone entirely.
    assert theme.TEAL != "#20808D"
    # TERRA is a separate semantic (ui.py callout border) and intentionally stays.
    assert theme.TERRA == "#A84B2F"


def test_theme_reexports_the_hybrid_workspace_roles():
    """Premium redesign: theme.py stays the compatibility surface for call
    sites that import from it, so the new light-workspace and dark-instrument
    roles must be reachable here without a second set of literals."""
    from src.tradelens.ui import design_system as ds

    assert theme.CANVAS == ds.TL_SURFACE_CANVAS
    assert theme.PAPER == ds.TL_SURFACE_PANEL
    assert theme.MIST == ds.TL_SURFACE_ELEVATED
    assert theme.INK == ds.TL_CONTENT_PRIMARY
    assert theme.HAIRLINE == ds.TL_LINE_HAIRLINE
    assert theme.RAIL == ds.TL_SURFACE_RAIL
    assert theme.CHART_STAGE == ds.TL_SURFACE_CHART
    assert theme.ACTION == ds.TL_ACCENT_ACTION


def test_theme_surface_tokens_follow_the_light_workspace():
    """BG/SURFACE/TEXT_PRIMARY drive theme.py's own CSS (.tl-empty-state,
    .tl-chat-*, .tl-grade-chip). Left on the dark values they would paint
    white-on-white once the app canvas turns light."""
    from src.tradelens.ui import design_system as ds

    assert theme.BG == ds.TL_SURFACE_CANVAS
    assert theme.SURFACE == ds.TL_SURFACE_PANEL
    assert theme.BORDER == ds.TL_LINE_HAIRLINE
    assert theme.TEXT_PRIMARY == ds.TL_CONTENT_PRIMARY
    assert theme.TEXT_MUTED == ds.TL_CONTENT_SECONDARY


def test_font_stacks_defined():
    # SP4: the app adopts the marketing site's faces so the brand reads as one
    # system. Inter/Space Grotesk were the pre-SP4 pair.
    assert theme.BODY_FONT == "Satoshi"
    assert theme.HEADING_FONT == "Schibsted Grotesk"
    assert theme.MONO_FONT == "JetBrains Mono"


def test_grade_colors_span_success_to_danger():
    # Grade ramp comes from design_system (outcome semantics): A-tier is
    # success green, F is danger red — never the legacy teal/terra pair.
    # Grade chips are read on PAPER, so the ramp follows the light-workspace
    # semantics rather than the brighter dark-instrument ones.
    from src.tradelens.ui import design_system as ds

    assert theme.GRADE_COLORS["A+"] == ds.TL_SUCCESS
    assert theme.GRADE_COLORS["F"] == ds.TL_DANGER
    assert theme.GRADE_COLORS["A+"] != theme.TEAL
    assert theme.GRADE_COLORS["F"] != theme.TERRA


def test_killzone_labels_present():
    assert theme.KILLZONE_LABELS["ny_am"] == "NY AM"


# ---------------------------------------------------------------------------
# Plotly template
# ---------------------------------------------------------------------------


def test_plotly_template_is_template_object():
    assert isinstance(theme.PLOTLY_TEMPLATE, go.layout.Template)


def test_plotly_template_paints_the_dark_chart_stage():
    """Charts are dark instruments inside the light workspace, so a figure
    carries its own stage instead of adopting the surface behind it. Left
    transparent, the bright mark ramp landed on the mineral canvas."""
    from src.tradelens.ui import design_system as ds

    layout = theme.PLOTLY_TEMPLATE.layout
    assert layout.paper_bgcolor == ds.TL_SURFACE_CHART
    assert layout.plot_bgcolor == ds.TL_SURFACE_CHART


def test_charts_pin_the_stage_explicitly_so_streamlit_cannot_repaint_it():
    """Streamlit's frontend injects the app theme's colours into every
    figure as EXPLICIT layout values, which beat template ones. A
    template-only stage therefore resolved to the light workspace on screen
    even though the template was correct. These keys are what survive."""
    from src.tradelens.ui import design_system as ds
    from src.tradelens.ui.components import charts

    assert charts._BASE_LAYOUT["plot_bgcolor"] == ds.TL_SURFACE_CHART
    assert charts._BASE_LAYOUT["paper_bgcolor"] == ds.TL_SURFACE_CHART
    assert charts._BASE_LAYOUT["font"]["color"] == ds.TL_CONTENT_PRIMARY
    # never a literal — the stage has exactly one definition
    assert "rgba(0,0,0,0)" not in repr(charts._BASE_LAYOUT)


def test_every_plotly_call_site_opts_out_of_streamlits_own_theme():
    """`st.plotly_chart` defaults to theme="streamlit", which repaints the
    figure in the app's theme and discards our template. With the workspace
    light that put bright teal marks on a near-white plot area — the stage
    was correct in the template and invisible on screen."""
    ui = ROOT / "src" / "tradelens" / "ui"
    sources = [p for p in ui.rglob("*.py") if "_archive" not in p.parts]
    call_sites = [
        p for p in sources if "st.plotly_chart(" in p.read_text(encoding="utf-8")
    ]
    assert call_sites, "expected at least one chart call site"
    for path in call_sites:
        # comments explain the flag too, so count code lines only
        code = "\n".join(
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#")
        )
        assert code.count("st.plotly_chart(") == code.count(
            "theme=None"
        ), f"{path.name} renders a chart without theme=None"


def test_rendered_figures_resolve_to_the_dark_stage():
    """End-to-end on a real figure, not just the constants.

    A figure that never sets the background resolves it from the registered
    default template at render time, so the contract is: the chart leaves
    the key unset, and the template it resolves against paints the stage.
    """
    import pandas as pd

    from src.tradelens.ui import design_system as ds
    from src.tradelens.ui.components import charts

    df = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2026-07-01", "2026-07-02", "2026-07-03"]),
            "pnl": [120.0, -45.0, 80.0],
            "cumulative_pnl": [120.0, 75.0, 155.0],
        }
    )
    fig = charts.equity_curve_chart(df)
    assert fig.layout.paper_bgcolor == ds.TL_SURFACE_CHART
    assert fig.layout.plot_bgcolor == ds.TL_SURFACE_CHART
    assert fig.layout.template.layout.paper_bgcolor == ds.TL_SURFACE_CHART
    # and the trace drawn on it is a bright mark, not a light-surface one
    assert fig.data[0].line.color == ds.TL_PRIMARY


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


def test_charts_pull_brand_colors_from_design_system():
    # Charts draw from design_system tokens, never the legacy theme.py
    # teal/terra pair and never hardcoded hex. Semantics: teal = brand
    # trajectory lines; green/red = positive/negative outcomes (matches
    # the KPI cards and table pnl-pos/pnl-neg colors).
    from src.tradelens.ui.components import charts
    from src.tradelens.ui import design_system as ds

    assert charts._TEAL == ds.TL_PRIMARY
    assert charts._POS == ds.TL_SUCCESS
    assert charts._NEG == ds.TL_DANGER
    # SP4 collapse: theme.TEAL now re-exports TL_PRIMARY, so equality with the
    # chart teal is the CORRECT state (pre-SP4 this asserted inequality against
    # the legacy #20808D). Outcome red still must not be the terra callout.
    assert charts._TEAL == theme.TEAL
    assert charts._NEG != theme.TERRA
