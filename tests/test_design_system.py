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


def _strip_keyframes(css: str) -> str:
    """Remove whole @keyframes blocks, braces and all.

    Their `from` / `to` / `50%` stops are keyframe selectors, not element
    selectors — scanning them for bare tags reports `from` as an unscoped
    selector, which is a false positive, not an R1 violation.
    """
    out, i = [], 0
    while True:
        start = css.find("@keyframes", i)
        if start == -1:
            out.append(css[i:])
            return "".join(out)
        out.append(css[i:start])
        depth, j = 0, css.find("{", start)
        if j == -1:
            return "".join(out)
        while j < len(css):
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        i = j + 1


def _top_level_selectors(css: str) -> list[str]:
    """Extract each selector group (text before a `{`), dropping at-rules."""
    css = css.replace("<style>", "").replace("</style>", "")
    css = re.sub(r"@import\s+url\([^)]*\)\s*;", "", css)
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    css = _strip_keyframes(css)
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


def test_dark_instrument_palette_is_unchanged():
    """The pre-redesign dark palette keeps its values and becomes the
    DARK INSTRUMENT family: chart marks, the navigation rail, and focused AI
    reading surfaces. charts.py reads these directly, so repointing them at
    the light-surface semantics would put dark green on a dark stage.
    """
    assert ds.TL_BG == "#0d1117"
    assert ds.TL_SURFACE == "#161b22"
    assert ds.TL_PRIMARY == "#00e5cc"
    assert ds.TL_SUCCESS == "#22c55e"
    assert ds.TL_DANGER == "#f56565"
    assert ds.TL_WARNING == "#f59e0b"


def test_hybrid_palette_uses_light_workspace_and_dark_rail() -> None:
    from src.tradelens.ui import design_system as ds

    assert ds.TL_CANVAS == "#F3F6F6"
    assert ds.TL_PAPER == "#FFFFFF"
    assert ds.TL_RAIL == "#0F171B"
    assert ds.TL_CHART_STAGE == "#101A1E"
    # The plan pinned #087F74. Measured as text on the mineral canvas it is
    # 4.496:1, four thousandths under the AA floor, so the token is one step
    # darker. Spec 8 requires these values to be contrast-tested, not copied.
    assert ds.TL_ACTION == "#087C71"
    assert ds.TL_FOCUS == "#00E5CC"


def test_focus_teal_and_legacy_primary_are_the_same_brand_color():
    """TL_FOCUS is the redesign's name for the bright teal; TL_PRIMARY is the
    legacy alias the existing pages still import. One color, two names — they
    must never drift into two teals."""
    assert ds.TL_FOCUS.lower() == ds.TL_PRIMARY.lower()


def test_light_workspace_semantics_are_separate_tokens():
    """Light surfaces need darker semantic forms than dark instruments.
    Keeping them under distinct names is what lets one palette serve both."""
    assert ds.TL_SUCCESS_INK == "#167A47"
    assert ds.TL_DANGER_INK == "#B53A43"
    # spec proposed #A76500; measured 4.29:1 on the mineral canvas (below AA)
    assert ds.TL_WARNING_INK == "#9C5F00"
    assert ds.TL_SUCCESS_INK != ds.TL_SUCCESS
    assert ds.TL_DANGER_INK != ds.TL_DANGER


def test_all_color_tokens_nonempty_strings():
    for name in dir(ds):
        if name.startswith("TL_") and not name.startswith("TL_FONT"):
            val = getattr(ds, name)
            assert isinstance(val, str) and val, f"{name} must be non-empty str"


def test_font_tokens_defined():
    # SP4 brand fonts — must match theme.py and the marketing site.
    assert "JetBrains Mono" in ds.TL_FONT_MONO
    assert "Satoshi" in ds.TL_FONT_BODY
    assert "Schibsted Grotesk" in ds.TL_FONT_HEADING
    assert "Inter" not in ds.TL_FONT_BODY  # pre-SP4 face, fully retired


def test_font_imports_match_theme_urls():
    # design_system and theme must request identical stylesheet URLs so the
    # browser fetches each font file once, not twice under different params.
    from src.tradelens.ui.components import theme

    assert ds._FONT_IMPORT == theme._FONT_IMPORT
    assert ds._FONT_IMPORT_FONTSHARE == theme._FONT_IMPORT_FONTSHARE


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
        # SP4 mobile pass: verified live on streamlit 1.50 (New Trade renders
        # six [data-testid="stTextInput"] wrappers with input children).
        "stTextInput",
        # Shell pass: both observed in the live sidebar DOM on streamlit
        # 1.50.0. stPageLink-NavLink is the anchor st.page_link renders;
        # stCaptionContainer wraps the "Signed in as" caption. Deliberately
        # NOT added: the st-emotion-cache-* class Streamlit puts on the
        # active nav link — that hash changes between releases.
        "stPageLink-NavLink",
        "stCaptionContainer",
        # Journal calendar mobile grid: both observed in the live DOM on
        # streamlit 1.50.0 (a calday button's ancestor chain is
        # stElementContainer → stVerticalBlock → stColumn → stHorizontalBlock).
        "stColumn",
        "stHorizontalBlock",
        # AI Reviews dark reading sheet: generated prose is rendered by
        # Streamlit's own markdown renderer, so it arrives as ordinary
        # elements inside this wrapper rather than as our classed markup.
        # Observed in the live DOM on streamlit 1.50.0.
        "stMarkdownContainer",
        # Touch-target pass on Streamlit's own controls. All four observed in
        # the live DOM at 375px on streamlit 1.50.0: stRadio wraps the lens
        # selector (option labels carry data-baseweb="radio", the widget's
        # own label carries data-testid="stWidgetLabel"); stDateInput wraps
        # an <input>; stSidebarCollapseButton wraps a <button> while
        # stExpandSidebarButton sits on the button itself.
        "stRadio",
        "stDateInput",
        # Playbook accordions: five <details> whose <summary> is the only way
        # into five of the six sections. Observed at 375px on 1.50.0.
        "stExpander",
        # Settings export and CSV import: both render their button outside
        # .stButton, so the shared floor never reached them — measured at
        # 40px on 1.50.0.
        "stDownloadButton",
        "stFileUploader",
        # Selectbox: the visible control is the [data-baseweb="select"]
        # wrapper, not the 22px a11y <input> inside it. Measured at 40px.
        "stSelectbox",
        "stSidebarCollapseButton",
        "stExpandSidebarButton",
    }
    used = set(re.findall(r'data-testid="([^"]+)"', ds.build_css()))
    assert used <= proven, f"unproven testids: {used - proven}"


def test_css_has_no_semantic_colored_side_borders():
    """PRODUCT.md anti-pattern: no COLORED side borders — the tinted-card
    look where a success/danger stripe does the work the copy should do.

    The rule is about semantic color, not about the border property: a
    neutral hairline is how a margin annotation (the Evidence Rail) and a
    ruled KPI strip are built. So the contract is stated precisely — every
    side border must resolve to a neutral structural token.
    """
    css = ds.build_css()
    neutral = {
        "var(--tl-hairline)",
        "var(--tl-mist)",
        "var(--tl-border)",
        "var(--tl-border-subtle)",
        "var(--tl-rule)",
    }
    declarations = re.findall(r"border-(?:left|right):\s*([^;]+);", css)
    assert declarations, "expected the ruled structure to use side borders"
    for decl in declarations:
        used = set(re.findall(r"var\(--tl-[a-z0-9-]+\)", decl))
        assert used, f"side border must use a token, not a literal: {decl!r}"
        assert used <= neutral, f"semantic side border: {decl!r}"


def test_insight_cards_still_carry_no_side_border():
    """The specific anti-pattern PRODUCT.md footnote 1 flagged."""
    css = ds.build_css()
    block = css[css.index(".tl-insight-card {") :][:600]
    assert "border-left" not in block
    assert "border-right" not in block


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


def test_banner_only_announces_when_the_caller_marks_it_dynamic():
    assert 'role="alert"' not in ds.render_banner("Static policy", "warning")
    announced = ds.render_banner(
        "Needed before you continue: Asset.", "warning", announce=True
    )
    assert 'role="alert"' in announced


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


def _site_var(name: str) -> str:
    css = (Path(__file__).resolve().parents[1] / "site" / "styles.css").read_text(
        encoding="utf-8"
    )
    m = re.search(rf"--{name}:\s*(#[0-9a-fA-F]{{6}})", css)
    assert m, f"--{name} not found in site/styles.css"
    return m.group(1).lower()


def test_app_and_marketing_site_share_one_brand_accent():
    """Seam guard, restated for the hybrid theme.

    The signed-in app is now a LIGHT workspace; the marketing site stays dark
    and frozen. Their backgrounds are deliberately different, so asserting a
    shared background would only assert the old design. What must not drift is
    the brand mark itself: one teal across the site -> app handoff.
    """
    assert ds.TL_FOCUS.lower() == _site_var("accent")


def test_marketing_site_palette_is_untouched_by_the_app_redesign():
    """The site is frozen for this phase. If a redesign commit edits its
    palette, that is out of scope and this fails."""
    assert _site_var("bg") == "#0d1117"
    assert _site_var("surface") == "#161b22"
    assert _site_var("accent") == "#00e5cc"


# ---------------------------------------------------------------------------
# WCAG contrast contract — measured, never asserted from the spec sheet
# ---------------------------------------------------------------------------


def _relative_luminance(hex_color: str) -> float:
    raw = hex_color.lstrip("#")
    channels = [int(raw[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [
        c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(foreground: str, background: str) -> float:
    """WCAG 2.1 relative-contrast ratio between two opaque hex colors."""
    lighter, darker = sorted(
        (_relative_luminance(foreground), _relative_luminance(background)),
        reverse=True,
    )
    return (lighter + 0.05) / (darker + 0.05)


def test_contrast_helper_matches_known_reference_ratios():
    assert round(contrast_ratio("#000000", "#FFFFFF"), 2) == 21.0
    assert round(contrast_ratio("#FFFFFF", "#FFFFFF"), 2) == 1.0


def _composite(overlay: str, alpha: float, backdrop: str) -> str:
    """Flatten an rgba wash over an opaque surface — contrast is measured
    against what the eye actually receives, not against the token beneath."""

    def channels(value: str) -> list[int]:
        raw = value.lstrip("#")
        return [int(raw[i : i + 2], 16) for i in (0, 2, 4)]

    top, base = channels(overlay), channels(backdrop)
    return "#%02X%02X%02X" % tuple(
        round(alpha * top[i] + (1 - alpha) * base[i]) for i in range(3)
    )


def test_light_workspace_text_pairs_meet_wcag_aa():
    """AA for normal text is 4.5:1. Every pair a trader actually reads on the
    light workspace is measured here, so a token tweak cannot quietly drop a
    label below threshold."""
    pairs = [
        ("ink on canvas", ds.TL_INK, ds.TL_CANVAS),
        ("ink on paper", ds.TL_INK, ds.TL_PAPER),
        ("ink on mist", ds.TL_INK, ds.TL_MIST),
        ("muted on canvas", ds.TL_MUTED, ds.TL_CANVAS),
        ("muted on paper", ds.TL_MUTED, ds.TL_PAPER),
        ("muted on mist", ds.TL_MUTED, ds.TL_MIST),
        ("action on canvas", ds.TL_ACTION, ds.TL_CANVAS),
        ("action on paper", ds.TL_ACTION, ds.TL_PAPER),
        ("white on action", ds.TL_PAPER, ds.TL_ACTION),
        ("white on action hover", ds.TL_PAPER, ds.TL_ACTION_HOVER),
        ("success ink on canvas", ds.TL_SUCCESS_INK, ds.TL_CANVAS),
        ("success ink on paper", ds.TL_SUCCESS_INK, ds.TL_PAPER),
        ("danger ink on canvas", ds.TL_DANGER_INK, ds.TL_CANVAS),
        ("danger ink on paper", ds.TL_DANGER_INK, ds.TL_PAPER),
        ("warning ink on canvas", ds.TL_WARNING_INK, ds.TL_CANVAS),
        ("warning ink on paper", ds.TL_WARNING_INK, ds.TL_PAPER),
    ]
    for name, fg, bg in pairs:
        ratio = contrast_ratio(fg, bg)
        assert ratio >= 4.5, f"{name} is {ratio:.2f}:1 (AA needs 4.5:1)"


def test_error_box_copy_is_legible_on_its_own_composited_surface():
    """The error treatment, measured against what actually renders.

    ``error_box`` used a literal #e0855f — a light terracotta picked for a
    dark surface. On the danger wash over paper it measures ~2.2:1. The
    message shown when something has already failed is the last text that
    should be unreadable, so the copy is ink and the hue is the border and
    mark, which only need the 3:1 non-text floor.
    """
    from src.tradelens.ui.components.ui import error_box

    assert "#e0855f" not in error_box("boom").lower()

    for surface in (ds.TL_CANVAS, ds.TL_PAPER):
        ground = _composite(ds.TL_DANGER_INK, 0.10, surface)
        copy_ratio = contrast_ratio(ds.TL_INK, ground)
        edge_ratio = contrast_ratio(ds.TL_DANGER_INK, ground)
        assert copy_ratio >= 4.5, f"error copy is {copy_ratio:.2f}:1"
        assert edge_ratio >= 3.0, f"error border is {edge_ratio:.2f}:1"
    # the retired literal, measured, so the regression is documented
    assert (
        contrast_ratio("#e0855f", _composite(ds.TL_DANGER_INK, 0.10, ds.TL_PAPER)) < 3.0
    )


def test_error_box_is_styled_by_the_design_system():
    css = ds.build_css()
    block = css[css.index(".tl-error-box {") :][:400]
    assert "var(--tl-danger-wash)" in block
    assert "color: var(--tl-ink)" in block
    assert "white-space: pre-wrap" in block


def test_semantic_washes_carry_ink_copy_and_a_hue_mark():
    """The badge/banner rule, enforced numerically.

    A 10% tint darkens its surface toward its own ink, so semantic text on
    its own wash measures 4.1-4.9:1 at every tint strength — the pattern
    fails, not the value. Copy on a wash is therefore INK (13-14:1) and the
    hue survives as a dot, which only has to clear the 3:1 non-text floor.
    """
    washes = [
        ("success", ds.TL_SUCCESS_INK),
        ("danger", ds.TL_DANGER_INK),
        ("warning", ds.TL_WARNING_INK),
        ("action", ds.TL_ACTION),
    ]
    for surface in (ds.TL_CANVAS, ds.TL_PAPER):
        for name, hue in washes:
            ground = _composite(hue, 0.10, surface)
            copy_ratio = contrast_ratio(ds.TL_INK, ground)
            mark_ratio = contrast_ratio(hue, ground)
            assert copy_ratio >= 4.5, f"ink on {name} wash is {copy_ratio:.2f}:1"
            assert mark_ratio >= 3.0, f"{name} mark is {mark_ratio:.2f}:1"


def test_no_semantic_hue_is_used_as_text_on_a_wash_or_mist():
    """Guards the rule at the CSS level, not just in the token maths: a
    variant that sets a wash background must not also set a semantic color.
    """
    css = ds.build_css()
    for variant in (
        ".tl-badge-success",
        ".tl-badge-danger",
        ".tl-badge-warning",
        ".tl-badge-primary",
        ".tl-banner-warning",
        ".tl-banner-info",
        ".tl-banner-danger",
        ".tl-confidence-high",
        ".tl-confidence-medium",
    ):
        rule = re.search(rf"{re.escape(variant)} \{{([^}}]*)\}}", css)
        assert rule, f"{variant} has no rule"
        body = rule.group(1)
        assert "wash" in body, f"{variant} should sit on a quiet ground"
        assert "color:" not in body, f"{variant} tints its own copy"


def test_dark_instrument_text_pairs_meet_wcag_aa():
    """The rail and the chart stage carry text too — they get the same bar."""
    pairs = [
        ("rail text on rail", ds.TL_TEXT, ds.TL_RAIL),
        ("rail muted on rail", ds.TL_TEXT_MUTED, ds.TL_RAIL),
        ("focus teal on rail", ds.TL_FOCUS, ds.TL_RAIL),
        ("stage text on stage", ds.TL_TEXT, ds.TL_CHART_STAGE),
        ("stage muted on stage", ds.TL_TEXT_MUTED, ds.TL_CHART_STAGE),
        ("chart success on stage", ds.TL_SUCCESS, ds.TL_CHART_STAGE),
        ("chart danger on stage", ds.TL_DANGER, ds.TL_CHART_STAGE),
        ("chart warning on stage", ds.TL_WARNING, ds.TL_CHART_STAGE),
    ]
    for name, fg, bg in pairs:
        ratio = contrast_ratio(fg, bg)
        assert ratio >= 4.5, f"{name} is {ratio:.2f}:1 (AA needs 4.5:1)"


def test_chart_marks_are_legible_on_the_stage_they_are_drawn_on():
    """The pair that matters for a chart is trace vs its own background, not
    trace vs the page. Non-text graphics need 3:1 (WCAG 1.4.11); the axis
    and tick text on the same stage needs the full 4.5:1."""
    from src.tradelens.ui.components import charts

    stage = ds.TL_CHART_STAGE
    assert ds.PLOTLY_TEMPLATE.layout.paper_bgcolor == stage
    marks = [
        ("trajectory teal", charts._TEAL),
        ("positive", charts._POS),
        ("negative", charts._NEG),
        ("neutral grey", charts._GRAY),
        ("reference line", charts._REF_LINE),
    ]
    for name, color in marks:
        ratio = contrast_ratio(color, stage)
        assert ratio >= 3.0, f"{name} mark is {ratio:.2f}:1 on the stage"

    text = [
        ("figure font", ds.PLOTLY_TEMPLATE.layout.font.color),
        ("x tick", ds.PLOTLY_TEMPLATE.layout.xaxis.tickfont.color),
        ("y tick", ds.PLOTLY_TEMPLATE.layout.yaxis.tickfont.color),
        ("legend", ds.PLOTLY_TEMPLATE.layout.legend.font.color),
    ]
    for name, color in text:
        ratio = contrast_ratio(color, stage)
        assert ratio >= 4.5, f"chart {name} is {ratio:.2f}:1 on the stage"


def test_every_colorway_entry_is_distinguishable_on_the_stage():
    for i, color in enumerate(ds.PLOTLY_TEMPLATE.layout.colorway):
        ratio = contrast_ratio(color, ds.TL_CHART_STAGE)
        assert ratio >= 3.0, f"colorway[{i}] {color} is {ratio:.2f}:1"


def test_streamlit_config_primary_matches_the_action_token():
    """Streamlit paints its own focus rings and widget accents from
    primaryColor. Drift there means the framework's teal and the design
    system's teal are two different colours on the same screen."""
    config = (
        Path(__file__).resolve().parents[1] / ".streamlit" / "config.toml"
    ).read_text(encoding="utf-8")
    primary = re.search(r'primaryColor\s*=\s*"(#[0-9a-fA-F]{6})"', config)
    background = re.search(r'backgroundColor\s*=\s*"(#[0-9a-fA-F]{6})"', config)
    secondary = re.search(r'secondaryBackgroundColor\s*=\s*"(#[0-9a-fA-F]{6})"', config)
    text = re.search(r'textColor\s*=\s*"(#[0-9a-fA-F]{6})"', config)
    assert primary and background and secondary and text
    assert primary.group(1).upper() == ds.TL_ACTION.upper()
    assert background.group(1).upper() == ds.TL_CANVAS.upper()
    assert secondary.group(1).upper() == ds.TL_PAPER.upper()
    assert text.group(1).upper() == ds.TL_INK.upper()
    assert re.search(r'base\s*=\s*"light"', config), "workspace base must be light"


def test_grade_ramp_is_legible_on_light_surfaces():
    """Grade chips sit on paper in the ledger and trade detail. The whole
    A -> F ramp has to clear AA there, not just its endpoints."""
    for grade in ("A", "B", "C", "D", "F"):
        color = getattr(ds, f"TL_GRADE_{grade}")
        ratio = contrast_ratio(color, ds.TL_PAPER)
        assert ratio >= 4.5, f"grade {grade} is {ratio:.2f}:1 on paper"


def test_focus_ring_meets_non_text_contrast():
    """WCAG 2.1 SC 1.4.11: UI component boundaries need 3:1."""
    assert contrast_ratio(ds.TL_ACTION, ds.TL_CANVAS) >= 3.0
    assert contrast_ratio(ds.TL_ACTION, ds.TL_PAPER) >= 3.0
    assert contrast_ratio(ds.TL_FOCUS, ds.TL_RAIL) >= 3.0


# ---------------------------------------------------------------------------
# Hybrid shell + premium primitives (CSS surface contract)
# ---------------------------------------------------------------------------


def test_css_declares_the_hybrid_surface_variables():
    css = ds.build_css()
    for var in (
        "--tl-canvas",
        "--tl-paper",
        "--tl-mist",
        "--tl-ink",
        "--tl-muted",
        "--tl-hairline",
        "--tl-rail",
        "--tl-chart-stage",
        "--tl-action",
        "--tl-focus",
    ):
        assert f"{var}:" in css, f"{var} not declared"


def test_every_color_literal_lives_in_the_token_block():
    """Spec 17: the design system is the single source of truth, so a colour
    may be written once — in :root — and referenced everywhere else. A
    literal in a component rule is how a stale brand colour survives a
    rebrand."""
    css = re.sub(r"/\*.*?\*/", "", ds.build_css(), flags=re.DOTALL)
    css = re.sub(r"@import\s+url\([^)]*\)\s*;", "", css)
    root = re.search(r":root \{.*?\n\}", css, re.DOTALL)
    assert root, ":root token block not found"
    components = css.replace(root.group(0), "")
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b", components), "raw hex outside :root"
    assert not re.findall(r"rgba\([^)]*\)", components), "raw rgba outside :root"


def test_no_pre_sp4_teal_survives_anywhere():
    """One brand teal. The legacy accent outlived two rebrands as an rgba()
    literal; this is the guard that stops the third. Scoped to declarations
    — a comment naming the retired value is documentation, not a use."""
    css = re.sub(r"/\*.*?\*/", "", ds.build_css(), flags=re.DOTALL).lower()
    assert "#00c2b2" not in css
    assert "0,194,178" not in css


def test_css_declares_the_three_typographic_roles():
    css = ds.build_css()
    assert "--tl-font-display:" in css
    assert "--tl-font-ui:" in css
    assert "--tl-font-mono:" in css


def test_type_roles_do_not_reintroduce_the_retired_face():
    """Spec 16 rejects generic Inter typography; SP4 retired the face."""
    assert "Inter" not in ds.build_css()


def test_navigation_rail_is_dark_and_workspace_is_light():
    css = ds.build_css()
    rail = css[css.index('[data-testid="stSidebar"] {') :][:240]
    assert "var(--tl-rail)" in rail
    assert "background: var(--tl-canvas)" in css


def test_css_styles_the_premium_primitives():
    css = ds.build_css()
    for cls in (
        ".tl-masthead",
        ".tl-kpi-strip",
        ".tl-evidence-rail",
        ".tl-finding",
        ".tl-readout",
        ".tl-filter-summary",
    ):
        assert f"{cls} {{" in css, f"{cls} has no styling"


def test_evidence_rail_reads_as_a_margin_annotation_not_a_card():
    """The signature is a ruled annotation. If it grows a filled background
    and a full border it has quietly become another card."""
    css = ds.build_css()
    block = css[css.index(".tl-evidence-rail {") :][:400]
    assert "border-left" in block
    assert "border-radius" not in block


def test_css_defines_motion_tokens_but_adds_no_transitions_to_primitives():
    """Task 1 locks timing; motion is applied only after static hierarchy is
    approved (plan: 'no motion is added in this task')."""
    css = ds.build_css()
    assert "--tl-ease-out: cubic-bezier(0.23, 1, 0.32, 1)" in css
    assert "--tl-ease-in-out: cubic-bezier(0.77, 0, 0.175, 1)" in css
    assert "--tl-ease-drawer: cubic-bezier(0.32, 0.72, 0, 1)" in css
    for cls in (".tl-kpi-strip", ".tl-evidence-rail", ".tl-finding", ".tl-masthead"):
        block = css[css.index(f"{cls} {{") :][:400]
        assert "transition" not in block, f"{cls} animates before the static pass"


def test_css_never_uses_the_transition_all_shorthand():
    """Emil: always name the properties that move."""
    assert "transition: all" not in ds.build_css()


def test_shadow_scale_collapses_to_one_elevation():
    """Spec 8: borders and spacing establish hierarchy before shadows; ONE
    low elevation token is permitted, for overlays and the mobile action bar."""
    css = ds.build_css()
    assert "--tl-shadow:" in css
    for retired in ("--tl-shadow-sm:", "--tl-shadow-md:", "--tl-shadow-lg:"):
        assert retired not in css, f"{retired} should have collapsed"


def test_radius_scale_matches_control_panel_overlay_tiers():
    """Spec 8: 6px controls, 8px panels, 10px overlays; no universal 16px."""
    css = ds.build_css()
    assert "--tl-radius-sm: 6px" in css
    assert "--tl-radius-md: 8px" in css
    assert "--tl-radius-lg: 10px" in css
    assert "16px" not in re.search(r"--tl-radius-[a-z]+: \d+px", css).group(0)


def test_ai_review_prose_has_a_readable_measure():
    """A weekly review is several hundred words in a full-width column.

    Unmeasured it reads as a wall and gets skimmed, which defeats the
    point of generating it. The audit asked for a 68-72ch measure.
    """
    css = ds.build_css()
    review_rules = css[css.index('[class*="st-key-tl_review_"] p,') :][:400]
    assert "max-width: 68ch" in review_rules
    assert "line-height" in review_rules
