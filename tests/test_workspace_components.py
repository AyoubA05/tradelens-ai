"""
Tests for src/tradelens/ui/components/workspace.py (premium redesign, Task 1).

workspace.py holds the shared presentation primitives of the hybrid
workspace: page masthead, ruled KPI strip, Evidence Rail, numbered research
finding, editorial readout, and filter summary.

Contracts asserted here:
- every renderer is PURE (returns HTML, never imports Streamlit);
- every renderer escapes user-controlled text;
- every renderer produces exactly ONE root element, so callers can drop the
  string into st.markdown(..., unsafe_allow_html=True) without Streamlit's
  markdown pass re-parenting stray siblings;
- every renderer exposes stable semantic class names the design system
  styles (pages never restyle these locally);
- optional fields are omitted entirely rather than rendered empty;
- unknown enum values degrade to a safe default instead of raising — these
  run inside a render path where an exception would blank the page.
"""

from html.parser import HTMLParser
from pathlib import Path

from src.tradelens.ui.components import workspace as ws
from src.tradelens.ui.components.workspace import (
    EvidenceItem,
    MetricItem,
    ResearchFinding,
    render_editorial_readout,
    render_evidence_rail,
    render_filter_summary,
    render_kpi_strip,
    render_research_finding,
    render_section_header,
    render_workspace_header,
)


class _RootCounter(HTMLParser):
    """Count top-level elements in a fragment (no void tags are emitted)."""

    def __init__(self) -> None:
        super().__init__()
        self.depth = 0
        self.roots = 0

    def handle_starttag(self, tag, attrs):  # noqa: D102 - parser callback
        if self.depth == 0:
            self.roots += 1
        self.depth += 1

    def handle_endtag(self, tag):  # noqa: D102 - parser callback
        self.depth -= 1


def _root_count(fragment: str) -> int:
    parser = _RootCounter()
    parser.feed(fragment)
    return parser.roots


def _evidence(**overrides) -> EvidenceItem:
    fields = {
        "evidence": "London killzone entries closed above 1R",
        "sample": "n=21 · Jul 1-24",
        "confidence": "medium",
        "limitation": None,
    }
    fields.update(overrides)
    return EvidenceItem(**fields)


_ALL_RENDERERS = (
    lambda: render_workspace_header("Overview", "Week in review"),
    lambda: render_workspace_header("Overview", "Week", eyebrow="NQ", meta="Jul"),
    lambda: render_kpi_strip([MetricItem("Net P&L", "$2,800")]),
    lambda: render_kpi_strip([]),
    lambda: render_evidence_rail(_evidence()),
    lambda: render_evidence_rail(_evidence(limitation="Directional only")),
    lambda: render_research_finding(ResearchFinding(1, "Title", "Body", _evidence())),
    lambda: render_editorial_readout("Readout", "Body", _evidence()),
    lambda: render_filter_summary([("Asset", "NQ")]),
    lambda: render_filter_summary([]),
    lambda: render_section_header("Performance"),
    lambda: render_section_header("Performance", "Last 30 days"),
)


# ---------------------------------------------------------------------------
# Module contract
# ---------------------------------------------------------------------------


def test_no_module_level_streamlit_import():
    """Pure module — services and tests must import it without Streamlit."""
    src = Path(ws.__file__).read_text(encoding="utf-8")
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import streamlit", "from streamlit")):
            assert line != stripped, f"top-level streamlit import: {line!r}"


def test_every_renderer_returns_exactly_one_root_element():
    for build in _ALL_RENDERERS:
        fragment = build()
        assert _root_count(fragment) == 1, f"multiple roots: {fragment[:80]!r}"


# ---------------------------------------------------------------------------
# Workspace header (page masthead)
# ---------------------------------------------------------------------------


def test_workspace_header_exposes_title_and_subtitle():
    html = render_workspace_header("Overview", "Where the week stands")
    assert 'class="tl-masthead"' in html
    assert "Overview" in html
    assert "Where the week stands" in html


def test_workspace_header_omits_absent_eyebrow_and_meta():
    html = render_workspace_header("Overview", "Sub")
    assert "tl-masthead-eyebrow" not in html
    assert "tl-masthead-meta" not in html


def test_workspace_header_renders_eyebrow_and_meta_when_given():
    html = render_workspace_header("Overview", "Sub", eyebrow="Demo data", meta="NQ")
    assert "tl-masthead-eyebrow" in html and "Demo data" in html
    assert "tl-masthead-meta" in html and "NQ" in html


def test_workspace_header_escapes_every_field():
    html = render_workspace_header("<b>T</b>", "<i>S</i>", eyebrow="<u>E</u>", meta="&")
    for raw in ("<b>", "<i>", "<u>"):
        assert raw not in html
    assert "&lt;b&gt;" in html and "&amp;" in html


# ---------------------------------------------------------------------------
# Ruled KPI strip
# ---------------------------------------------------------------------------


def test_kpi_strip_renders_one_cell_per_metric():
    html = render_kpi_strip(
        [
            MetricItem("Net P&L", "$2,800", detail="12 trades", tone="positive"),
            MetricItem("Win rate", "61.3%"),
        ]
    )
    assert 'class="tl-kpi-strip"' in html
    assert html.count("tl-kpi-cell") == 2
    assert "Net P&amp;L" in html
    assert "61.3%" in html


def test_kpi_strip_announces_tone_as_text_not_only_as_an_attribute():
    """`data-tone` styles and tests the cell but is invisible to assistive
    technology — a screen reader announces text. Without a spoken word, a
    losing month and a winning one read out identically."""
    negative = render_kpi_strip([MetricItem("Net P&L", "-$120", tone="negative")])
    assert "tl-kpi-cell tone-negative" in negative
    assert 'class="tl-visually-hidden">Down: ' in negative

    positive = render_kpi_strip([MetricItem("Net P&L", "$120", tone="positive")])
    assert 'class="tl-visually-hidden">Up: ' in positive

    warning = render_kpi_strip([MetricItem("Risk", "2.4R", tone="warning")])
    assert 'class="tl-visually-hidden">Needs attention: ' in warning


def test_kpi_strip_stays_silent_for_neutral_figures():
    """Announcing "neutral" before every unremarkable number is noise, and
    it is what makes screen-reader users turn a page off."""
    html = render_kpi_strip([MetricItem("Trades", "60")])
    assert "tl-visually-hidden" not in html
    assert 'data-tone="neutral"' in html


def test_kpi_spoken_tone_is_hidden_from_sighted_readers():
    """The word must not appear on screen — the colour already says it."""
    from src.tradelens.ui import design_system as ds

    css = ds.build_css()
    block = css[css.index(".tl-visually-hidden {") :][:320]
    assert "clip-path: inset(50%)" in block
    # display:none / visibility:hidden would drop it from the a11y tree too
    assert "display: none" not in block
    assert "visibility: hidden" not in block


def test_kpi_strip_unknown_tone_falls_back_to_neutral():
    html = render_kpi_strip([MetricItem("X", "1", tone="chartreuse")])
    assert "tone-neutral" in html
    assert "chartreuse" not in html


def test_kpi_strip_omits_detail_when_absent():
    html = render_kpi_strip([MetricItem("Trades", "60")])
    assert "tl-kpi-detail" not in html


def test_kpi_strip_empty_still_renders_one_root():
    html = render_kpi_strip([])
    assert html == '<div class="tl-kpi-strip"></div>'


def test_kpi_strip_escapes_user_text():
    html = render_kpi_strip([MetricItem("<b>L</b>", "<b>V</b>", detail="<b>D</b>")])
    assert "<b>" not in html
    assert html.count("&lt;b&gt;") == 3


# ---------------------------------------------------------------------------
# Evidence Rail — the signature component
# ---------------------------------------------------------------------------


def test_evidence_rail_escapes_copy_and_exposes_semantic_fields():
    item = EvidenceItem(
        evidence="<b>21 trades</b>",
        sample="n=21",
        confidence="medium",
        limitation="Directional only",
    )
    html = render_evidence_rail(item)
    assert "<b>21 trades</b>" not in html
    assert "&lt;b&gt;21 trades&lt;/b&gt;" in html
    assert 'class="tl-evidence-rail"' in html
    assert "Evidence" in html
    assert "Sample" in html
    assert "Confidence" in html
    assert "Limitation" in html


def test_evidence_rail_omits_limitation_when_absent():
    html = render_evidence_rail(_evidence(limitation=None))
    assert "Limitation" not in html
    assert "Evidence" in html and "Sample" in html and "Confidence" in html


def test_evidence_rail_confidence_is_labelled_and_classed():
    html = render_evidence_rail(_evidence(confidence="high"))
    assert "tl-evidence-confidence conf-high" in html
    # the level is spelled out, never encoded as color alone
    assert "High" in html


def test_evidence_rail_unknown_confidence_degrades_to_low():
    html = render_evidence_rail(_evidence(confidence="certain"))
    assert "conf-low" in html
    assert "certain" not in html


def test_evidence_rail_uses_definition_semantics():
    """Evidence is label/value data — it renders as a definition list, not
    a stack of divs, so screen readers announce the pairing."""
    html = render_evidence_rail(_evidence(limitation="Small sample"))
    assert "<dl" in html and html.count("<dt") == 3 and html.count("<dd") == 3


# ---------------------------------------------------------------------------
# Numbered research finding
# ---------------------------------------------------------------------------


def test_research_finding_numbers_are_zero_padded_reading_order():
    html = render_research_finding(
        ResearchFinding(2, "Late entries", "Body text", _evidence())
    )
    assert 'class="tl-finding"' in html
    assert "02" in html
    assert "Late entries" in html
    assert "Body text" in html


def test_research_finding_carries_its_own_evidence_rail():
    html = render_research_finding(
        ResearchFinding(1, "T", "B", _evidence(limitation="Directional only"))
    )
    assert 'class="tl-evidence-rail"' in html
    assert "Directional only" in html


def test_research_finding_escapes_user_text():
    html = render_research_finding(
        ResearchFinding(1, "<b>T</b>", "<i>B</i>", _evidence())
    )
    assert "<b>" not in html and "<i>" not in html
    assert "&lt;b&gt;" in html


# ---------------------------------------------------------------------------
# Editorial readout
# ---------------------------------------------------------------------------


def test_editorial_readout_composes_title_body_and_evidence():
    html = render_editorial_readout(
        "What changed",
        "Expectancy improved on London sessions.",
        _evidence(limitation="Directional only"),
    )
    assert 'class="tl-readout"' in html
    assert "What changed" in html
    assert "Expectancy improved" in html
    assert 'class="tl-evidence-rail"' in html


def test_editorial_readout_escapes_user_text():
    html = render_editorial_readout("<b>T</b>", "<i>B</i>", _evidence())
    assert "<b>" not in html and "<i>" not in html


# ---------------------------------------------------------------------------
# Filter summary
# ---------------------------------------------------------------------------


def test_filter_summary_renders_key_value_pairs():
    html = render_filter_summary([("Asset", "NQ"), ("Session", "London")])
    assert 'class="tl-filter-summary"' in html
    assert html.count("tl-filter-chip") == 2
    assert "Asset" in html and "NQ" in html


def test_filter_summary_empty_states_what_is_shown():
    html = render_filter_summary([])
    assert "tl-filter-chip" not in html
    assert "All trades" in html


def test_filter_summary_escapes_user_text():
    html = render_filter_summary([("<b>K</b>", "<b>V</b>")])
    assert "<b>" not in html
    assert html.count("&lt;b&gt;") == 2


# ---------------------------------------------------------------------------
# Section header — one builder, shared by design_system and components/ui
# ---------------------------------------------------------------------------


def test_section_header_with_and_without_subtitle():
    with_sub = render_section_header("Today", "Mon 6 Jul")
    without = render_section_header("Today")
    assert "tl-section-subtitle" in with_sub
    assert "tl-section-subtitle" not in without
    assert '<h2 class="tl-section-title">Today</h2>' in with_sub
    assert '<div class="tl-section-title">' not in with_sub


def test_section_header_is_the_single_source_for_both_call_sites():
    """design_system and components/ui must delegate here, not duplicate
    the markup — three copies of one header is how they drift apart."""
    from src.tradelens.ui import design_system as ds
    from src.tradelens.ui.components.ui import section_header

    expected = render_section_header("Performance", "Last 30 days")
    assert ds.render_section_header("Performance", "Last 30 days") == expected
    assert section_header("Performance", "Last 30 days") == expected
