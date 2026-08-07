"""One reading shell, two adapters.

Patterns builds a structured ResearchNote; Weekly and Daily produce
content_md. Both must arrive at the same five-region note anatomy, or the
product has two different ideas of what a review looks like (D6).
"""

from pathlib import Path

import pytest

from src.tradelens.ui.components.review_reader import (
    ReviewView,
    build_note_regions,
    clamp_section,
    view_from_markdown,
    view_from_note,
)
from src.tradelens.ui.components.workspace import (
    EvidenceItem,
    ResearchFinding,
    ResearchNote,
)

SHELL = (
    Path(__file__).resolve().parents[1] / "src/tradelens/ui/components/review_reader.py"
)

_EVIDENCE = EvidenceItem(
    evidence="18 completed trades",
    sample="n=18 of 25",
    confidence="medium",
    limitation="One session dominates the sample.",
)


def _note(**over):
    base = dict(
        title="Patterns",
        thesis="You size up after losses.",
        findings=(ResearchFinding(1, "Revenge sizing", "body", _EVIDENCE),),
        actions=("Re-read Tuesday's entries.",),
        evidence_used=("25 trades",),
        sample="n=25",
        limitation="Small sample.",
    )
    base.update(over)
    return ResearchNote(**base)


# ---------------------------------------------------------------------------
# The plan's tests.
# ---------------------------------------------------------------------------


def test_a_structured_note_and_markdown_reach_the_same_shape():
    note = _note()
    md = view_from_markdown(
        title="Weekly Recap",
        sample="n=25",
        content_md="You size up after losses.\n\n## Revenge sizing\nbody",
        evidence=_EVIDENCE,
        actions=("Re-read Tuesday's entries.",),
        evidence_used=("25 trades",),
    )
    assert isinstance(view_from_note(note), ReviewView)
    assert view_from_note(note).thesis_md.strip() == md.thesis_md.strip()


def test_the_thesis_is_the_lead_paragraph_and_is_not_repeated_in_a_section():
    view = view_from_markdown(
        title="Weekly Recap",
        sample="n=9",
        content_md="Lead claim.\n\n## Detail\nbody",
        evidence=_EVIDENCE,
    )
    assert view.thesis_md == "Lead claim."
    assert "Lead claim." not in view.document.sections[0].body_md


def test_the_evidence_rail_appears_once_per_note_not_under_every_paragraph():
    view = view_from_markdown(
        title="Weekly Recap",
        sample="n=9",
        content_md="Lead.\n\n## A\na\n\n## B\nb",
        evidence=_EVIDENCE,
    )
    html = build_note_regions(view)
    assert html.count("tl-evidence-rail") == 1


def test_read_full_note_renders_every_original_section():
    """Generated text is never truncated or discarded."""
    content = "Lead.\n\n## A\nalpha\n\n## B\nbeta"
    view = view_from_markdown(
        title="W", sample="n=1", content_md=content, evidence=_EVIDENCE
    )
    full = view.thesis_md + "".join(s.body_md for s in view.document.sections)
    for token in ("Lead.", "alpha", "beta"):
        assert token in full


def test_the_active_section_clamps_when_a_regenerated_note_has_fewer_sections():
    assert clamp_section(index=5, total=2) == 1
    assert clamp_section(index=-1, total=2) == 0
    assert clamp_section(index=0, total=0) == 0


# ---------------------------------------------------------------------------
# The plan's Step 7 safety guards.
# ---------------------------------------------------------------------------


def test_the_reading_shell_added_no_prompt_call_or_service_edit():
    source = SHELL.read_text(encoding="utf-8")
    for banned in ("import anthropic", "from src.tradelens.prompts", "generate_"):
        assert banned not in source, f"the shell reaches past presentation: {banned}"


def test_generated_prose_never_takes_the_unsafe_html_path():
    """Authored chrome may use unsafe_allow_html; model output may not.

    Asserted through the AST, not a text window. `near()` scans a fixed
    character radius, so it reports on whatever happens to sit nearby — it
    would pass a file that renders the thesis unsafely three lines further
    down than the window reached, and fail a safe one that merely mentions
    the name close to unrelated chrome.
    """
    import ast

    tree = ast.parse(SHELL.read_text(encoding="utf-8"))
    unsafe = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not any(
            k.arg == "unsafe_allow_html"
            and isinstance(k.value, ast.Constant)
            and k.value.value is True
            for k in node.keywords
        ):
            continue
        rendered = ast.dump(
            ast.Module(body=[ast.Expr(a) for a in node.args], type_ignores=[])
        )
        for generated in ("thesis_md", "body_md", "content_md", "intro_md"):
            if generated in rendered:
                unsafe.append((node.lineno, generated))
    assert not unsafe, f"model output on an HTML-allowing path: {unsafe}"


# ---------------------------------------------------------------------------
# Properties the plan's tests state but do not exercise.
# ---------------------------------------------------------------------------


def test_a_note_that_opens_on_a_heading_still_gets_a_lead_paragraph():
    """Weekly and Daily output does not reliably start with prose. With no
    intro the plan's adapter would leave the thesis empty and the note would
    open with no lead claim at all."""
    view = view_from_markdown(
        title="W",
        sample="n=9",
        content_md="## What happened\nLead claim.\n\nMore detail.\n\n## Next\nx",
        evidence=_EVIDENCE,
    )
    assert view.thesis_md == "Lead claim."
    assert "Lead claim." not in view.document.sections[0].body_md
    assert "More detail." in view.document.sections[0].body_md


def test_lifting_the_lead_paragraph_loses_nothing():
    content = "## What happened\nLead claim.\n\nMore detail.\n\nEven more."
    view = view_from_markdown(
        title="W", sample="n=1", content_md=content, evidence=_EVIDENCE
    )
    rebuilt = view.thesis_md + "\n" + "".join(s.body_md for s in view.document.sections)
    for token in ("Lead claim.", "More detail.", "Even more."):
        assert token in rebuilt


def test_a_notes_stated_confidence_is_its_floor_not_its_peak():
    """The rail qualifies the whole note. Quoting the strongest finding would
    describe the weakest claim on the page as high confidence."""
    note = _note(
        findings=(
            ResearchFinding(1, "A", "b", EvidenceItem("e", "n=20", "high", None)),
            ResearchFinding(2, "B", "b", EvidenceItem("e", "n=3", "low", None)),
        )
    )
    assert view_from_note(note).evidence.confidence == "low"


def test_a_note_with_no_findings_states_low_confidence_rather_than_guessing():
    assert view_from_note(_note(findings=())).evidence.confidence == "low"


def test_every_finding_becomes_exactly_one_navigable_section():
    note = _note(
        findings=tuple(
            ResearchFinding(n, f"F{n}", f"body {n}", _EVIDENCE) for n in range(1, 5)
        )
    )
    view = view_from_note(note)
    assert [s.title for s in view.document.sections] == ["F1", "F2", "F3", "F4"]
    assert len({s.id for s in view.document.sections}) == 4


def test_the_structured_adapter_keeps_the_rail_to_one_as_well():
    """Patterns rendered `render_research_note`, which embeds a rail inside
    EVERY numbered finding — four findings meant four stacked rails, against
    §7.2's "once per note, not under every paragraph"."""
    note = _note(
        findings=tuple(
            ResearchFinding(n, f"F{n}", "body", _EVIDENCE) for n in range(1, 5)
        )
    )
    assert build_note_regions(view_from_note(note)).count("tl-evidence-rail") == 1


@pytest.mark.parametrize("junk", [None, 123, [], {}])
def test_a_view_survives_junk_content(junk):
    """This runs inside a render path — raising would blank the page."""
    view = view_from_markdown(
        title="W", sample="n=0", content_md=junk, evidence=_EVIDENCE
    )
    assert view.thesis_md == ""
    assert view.document.sections == ()


@pytest.mark.parametrize("index", [None, "3", -99, 10**9])
def test_clamp_survives_a_stored_index_of_any_shape(index):
    """The index comes out of session state, which outlives the document and
    is not typed."""
    assert 0 <= clamp_section(index=index, total=3) <= 2


def test_caller_values_are_escaped_in_the_chrome():
    view = view_from_markdown(
        title="<script>x</script>",
        sample="n=1 & rising",
        content_md="Lead.",
        evidence=EvidenceItem("<b>e</b>", "n=1", "low", "<i>lim</i>"),
        actions=("<img src=x>",),
        evidence_used=("<svg/onload=1>",),
    )
    html = build_note_regions(view)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    for raw in ("<b>e</b>", "<i>lim</i>", "<img src=x>", "<svg/onload=1>"):
        assert raw not in html


def test_the_shell_is_importable_without_streamlit_being_started():
    """`st` is a parameter, not an import, so the pure half stays testable."""
    source = SHELL.read_text(encoding="utf-8")
    assert "import streamlit" not in source


def test_dollar_amounts_are_not_parsed_as_math():
    """Paired amounts render as a LaTeX span and garble the money between
    them. The rule lived on the page and reached only two of three lenses."""
    from src.tradelens.ui.components.review_reader import _md_safe

    assert _md_safe("won $1,000 and lost $500") == "won \\$1,000 and lost \\$500"
    assert _md_safe("already \\$5") == "already \\$5"
