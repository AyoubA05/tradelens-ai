"""The parser is presentation only.

It never rewrites what the model produced: every section keeps its original
Markdown, so `Read full note` can always render the complete response. A
parser that dropped content would silently discard a trader's review.
"""

import re
from pathlib import Path

import pytest

from src.tradelens.ui.components.review_document import (
    ReviewDocument,
    ReviewSection,
    parse_review_markdown,
)


def test_blank_content_returns_an_empty_document():
    doc = parse_review_markdown("")
    assert doc == ReviewDocument(intro_md="", sections=())
    assert doc.is_empty is True


def test_content_with_no_headings_returns_one_fallback_section():
    doc = parse_review_markdown("Just a paragraph of review prose.")
    assert len(doc.sections) == 1
    assert isinstance(doc.sections[0], ReviewSection)
    assert doc.sections[0].body_md == "Just a paragraph of review prose."


def test_prose_before_the_first_heading_becomes_the_intro():
    doc = parse_review_markdown("Lead sentence.\n\n## What happened\nBody.")
    assert doc.intro_md == "Lead sentence."
    assert doc.sections[0].title == "What happened"


def test_both_h2_and_h3_open_a_section():
    doc = parse_review_markdown("## A\nx\n### B\ny")
    assert [s.level for s in doc.sections] == [2, 3]
    assert [s.title for s in doc.sections] == ["A", "B"]


def test_original_markdown_is_preserved_verbatim():
    body = "- one\n- two\n\n**bold** and `code`"
    doc = parse_review_markdown(f"## Findings\n{body}")
    assert doc.sections[0].body_md == body


def test_duplicate_headings_get_deterministic_unique_ids():
    doc = parse_review_markdown("## Risk\na\n## Risk\nb")
    ids = [s.id for s in doc.sections]
    assert ids[0] != ids[1]
    assert parse_review_markdown("## Risk\na\n## Risk\nb").sections[1].id == ids[1]


def test_headings_inside_fenced_code_are_not_sections():
    doc = parse_review_markdown("## Real\n```\n## Not a heading\n```\n")
    assert len(doc.sections) == 1
    assert "## Not a heading" in doc.sections[0].body_md


def test_a_tilde_fence_also_protects_its_contents():
    doc = parse_review_markdown("## Real\n~~~\n## Not a heading\n~~~\n")
    assert len(doc.sections) == 1


def test_no_section_content_is_ever_dropped():
    source = "intro\n\n## A\nalpha\n\n## B\nbeta\n"
    doc = parse_review_markdown(source)
    rebuilt = doc.intro_md + "".join(s.body_md for s in doc.sections)
    for token in ("intro", "alpha", "beta"):
        assert token in rebuilt


@pytest.mark.parametrize("junk", [None, 123, [], {}])
def test_non_string_input_degrades_to_an_empty_document(junk):
    """This runs inside a render path — raising would blank the page."""
    assert parse_review_markdown(junk).is_empty is True


def test_a_backtick_fence_is_not_closed_by_tildes():
    doc = parse_review_markdown("## Real\n```\n~~~\n## Still code\n```\n## After\nx")
    assert [s.title for s in doc.sections] == ["Real", "After"]


def test_an_unclosed_fence_swallows_the_rest_rather_than_raising():
    doc = parse_review_markdown("## Real\n```\n## Not a heading\n")
    assert len(doc.sections) == 1


def test_a_heading_with_no_alphanumerics_still_gets_an_id():
    doc = parse_review_markdown("## ???\nbody")
    assert doc.sections[0].id == "section"


# ---------------------------------------------------------------------------
# Properties the plan's tests state but do not actually exercise.
# ---------------------------------------------------------------------------


def test_ids_are_unique_even_when_a_title_looks_like_a_collision_suffix():
    """Ids are what Task 12 selects a section by, so two sections sharing one
    is not cosmetic — it opens the wrong section.

    Counting per base is not enough. "Risk 2" legitimately slugs to `risk-2`;
    a later duplicate "Risk", numbered on its own counter, claims `risk-2`
    too. The plan's `test_duplicate_headings_get_deterministic_unique_ids`
    compares two *identical* headings and never meets this.
    """
    doc = parse_review_markdown("## Risk 2\na\n## Risk\nb\n## Risk\nc")
    ids = [s.id for s in doc.sections]
    assert len(set(ids)) == len(ids), f"duplicate ids: {ids}"


def test_ids_stay_unique_across_a_long_run_of_near_collisions():
    source = "".join(
        f"## {t}\nbody\n"
        for t in ("Risk", "Risk", "Risk 2", "Risk-2", "risk 3", "Risk")
    )
    ids = [s.id for s in parse_review_markdown(source).sections]
    assert len(set(ids)) == len(ids), f"duplicate ids: {ids}"


def test_ids_are_stable_across_repeated_parses():
    """A rerun must not move the reader's selection."""
    source = "## Risk 2\na\n## Risk\nb\n## Risk\nc"
    first = [s.id for s in parse_review_markdown(source).sections]
    assert first == [s.id for s in parse_review_markdown(source).sections]


def test_a_closing_fence_may_be_longer_than_the_one_it_opened():
    """CommonMark closes a fence with a run at least as long. A model quoting
    Markdown emits a ```` block containing ``` blocks, and a length-blind
    parser toggles out on the inner one — turning the rest of the quoted code
    into headings."""
    doc = parse_review_markdown(
        "## Real\n````\n```\n## Not a heading\n```\n````\n## After\nx"
    )
    assert [s.title for s in doc.sections] == ["Real", "After"]


def test_a_fence_with_an_info_string_does_not_close_an_open_fence():
    """```python opens a block; it never closes one."""
    doc = parse_review_markdown(
        "## Real\n```\n```python\n## Not a heading\n```\n## After\nx"
    )
    assert [s.title for s in doc.sections] == ["Real", "After"]


def test_an_atx_closing_sequence_is_not_part_of_the_title():
    """`## Findings ##` is a heading titled "Findings". Left in, the hashes
    render inside the section title and ride into its id."""
    doc = parse_review_markdown("## Findings ##\nbody")
    assert doc.sections[0].title == "Findings"
    assert doc.sections[0].id == "findings"


def test_every_non_heading_line_survives_the_round_trip():
    """The plan's version of this checks three tokens appear somewhere. This
    asserts the actual property: nothing but the heading lines is lost."""
    source = (
        "Lead.\n\n## A\nalpha one\nalpha two\n\n"
        "### A detail\n- bullet\n\n## B\n> quote\n\n```\ncode ## here\n```\n"
    )
    doc = parse_review_markdown(source)
    rebuilt = doc.intro_md + "\n" + "\n".join(s.body_md for s in doc.sections)
    for line in source.splitlines():
        if re.match(r"^#{2,3}\s+\S", line) or not line.strip():
            continue
        assert line in rebuilt, f"lost: {line!r}"


def test_the_parser_imports_nothing_from_streamlit_or_the_services():
    source = (
        Path(__file__).resolve().parents[1]
        / "src/tradelens/ui/components/review_document.py"
    ).read_text(encoding="utf-8")
    for banned in ("import streamlit", "from src.tradelens.services", "requests"):
        assert banned not in source


def test_the_parser_holds_no_state_between_documents():
    """Ids are scoped to one document. A module-level `taken` would number
    the second reader's sections from where the first left off."""
    a = parse_review_markdown("## Risk\nx")
    b = parse_review_markdown("## Risk\ny")
    assert a.sections[0].id == b.sections[0].id == "risk"
