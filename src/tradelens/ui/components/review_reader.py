"""One reading shell for the three AI Review lenses.

Patterns builds a structured `ResearchNote`; Weekly Recap and Daily Debrief
produce `content_md`. Before this, those were two different renderings — so the
product had two ideas of what a review looks like (D6). Two adapters bring both
to the same `ReviewView`, and one shell renders it.

The split of responsibility is deliberate and is what keeps this testable
without a browser:

* `build_note_regions` is **pure**. It returns the note's chrome — header,
  Evidence Rail, limitation, next actions, evidence disclosure — with every
  caller value escaped, exactly as `workspace.py`'s builders do.
* Generated Markdown is **never** embedded in that HTML. The thesis and each
  section body are handed separately to `st.markdown` with HTML off, which is
  the only path model output is allowed to take.

No prompts, no AI calls, no service edits, no database. This is presentation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from src.tradelens.ui.components.review_document import (
    ReviewDocument,
    ReviewSection,
    parse_review_markdown,
)
from src.tradelens.ui.components.workspace import (
    EvidenceItem,
    ResearchNote,
    render_evidence_disclosure,
    render_evidence_rail,
)

# Escaping is the shared workspace rule; import it rather than re-deriving it.
from html import escape

# Ordered weakest-first. A note's stated confidence is the floor across its
# findings, never the peak: a rail that quotes the strongest finding would
# describe the whole note as more certain than its weakest claim.
_CONFIDENCE_ORDER = ("low", "medium", "high")


@dataclass(frozen=True)
class ReviewView:
    """One review, in the shape the shell reads.

    `thesis_md` is lifted OUT of `document`, so `document.sections` never
    repeats it — the lead claim appears once, at the top, and the sections
    below it are the support rather than a restatement.
    """

    title: str
    sample: str
    thesis_md: str
    document: ReviewDocument
    evidence: EvidenceItem
    actions: Sequence[str]
    evidence_used: Sequence[str]


def period_stats(trades) -> dict:
    """The five period figures every lens's strip reads, in one shape.

    §7.6 asks for one strip on all three lenses, same builder, same cells.
    Weekly and Daily already receive this dict from their own service; only
    Patterns had nothing, and it had nothing because there was nowhere to get
    it from that did not mean recomputing on the page.

    Nothing is calculated here. Each figure comes from the approved metrics
    service and is only assembled into the shape `render_kpi_strip` reads.
    """
    import math

    import pandas as pd

    from src.tradelens.services.metrics import (
        compute_basic_metrics,
        compute_profit_factor_raw,
        total_edge_leak,
    )

    if trades is None or not isinstance(trades, pd.DataFrame) or trades.empty:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "profit_factor": None,
            "total_edge_leak": 0.0,
        }
    m = compute_basic_metrics(trades)
    pf = compute_profit_factor_raw(trades)
    return {
        "trades": int(m["total_trades"]),
        "win_rate": m["win_rate"],
        # None means "wins with no losses"; the strip renders that as ∞. An
        # inf float would not survive being stored or serialised, which is
        # why the weekly service uses the same convention.
        "profit_factor": None if math.isinf(pf) else pf,
        "total_pnl": m["total_pnl"],
        "total_edge_leak": total_edge_leak(trades),
    }


def clamp_section(*, index: int, total: int) -> int:
    """A section index that is always safe to use.

    A regenerated note can have fewer sections than the one it replaced, and
    the reader's stored index outlives the document it pointed into. Clamping
    here means every caller gets the same answer instead of each guarding.
    """
    if total <= 0:
        return 0
    try:
        value = int(index)
    except (TypeError, ValueError):
        return 0
    return max(0, min(value, total - 1))


def _split_lead(text: str) -> tuple:
    """First paragraph, then the rest — losing nothing.

    Used only where a document has no prose before its first heading. The
    parser's promise is that it never rewrites generated Markdown, and this
    keeps it: the lead is moved, not edited, and the remainder is returned
    intact so the two together are still the original.
    """
    stripped = text.strip()
    if not stripped:
        return "", ""
    parts = stripped.split("\n\n", 1)
    lead = parts[0].strip()
    rest = parts[1].strip() if len(parts) > 1 else ""
    return lead, rest


def view_from_markdown(
    *,
    title: str,
    sample: str,
    content_md: object,
    evidence: EvidenceItem,
    actions: Sequence[str] = (),
    evidence_used: Sequence[str] = (),
) -> ReviewView:
    """Adapter for a generated Markdown note (Weekly Recap, Daily Debrief)."""
    document = parse_review_markdown(content_md)
    thesis = document.intro_md.strip()
    sections = document.sections

    if not thesis and sections:
        # A note that opens straight into a heading still deserves a lead
        # paragraph. Take it from the first section rather than inventing one,
        # and keep the remainder so nothing is dropped.
        lead, rest = _split_lead(sections[0].body_md)
        thesis = lead
        first = sections[0]
        sections = (
            ReviewSection(
                id=first.id, level=first.level, title=first.title, body_md=rest
            ),
        ) + tuple(sections[1:])

    return ReviewView(
        title=title,
        sample=sample,
        thesis_md=thesis,
        document=ReviewDocument(intro_md="", sections=tuple(sections)),
        evidence=evidence,
        actions=tuple(actions),
        evidence_used=tuple(evidence_used),
    )


def view_from_note(note: ResearchNote) -> ReviewView:
    """Adapter for a structured note (Patterns).

    Each numbered finding becomes one section, so the shell navigates a
    structured note and a generated one the same way.
    """
    levels = [
        str(f.evidence.confidence)
        for f in note.findings
        if str(f.evidence.confidence) in _CONFIDENCE_ORDER
    ]
    floor = (
        min(levels, key=_CONFIDENCE_ORDER.index)  # weakest finding sets the floor
        if levels
        else "low"
    )

    sections = tuple(
        ReviewSection(
            id=f"finding-{f.number}",
            level=2,
            title=str(f.title),
            body_md=str(f.body),
        )
        for f in note.findings
    )
    return ReviewView(
        title=str(note.title),
        sample=str(note.sample),
        thesis_md=str(note.thesis),
        document=ReviewDocument(intro_md="", sections=sections),
        evidence=EvidenceItem(
            evidence="Your own journalled trades",
            sample=str(note.sample),
            confidence=floor,
            limitation=str(note.limitation) or None,
        ),
        actions=tuple(note.actions),
        evidence_used=tuple(note.evidence_used),
    )


# ---------------------------------------------------------------------------
# Pure chrome. No generated Markdown reaches any of these.
# ---------------------------------------------------------------------------


def _head_html(view: ReviewView) -> str:
    return (
        '<header class="tl-note-head">'
        f'<h2 class="tl-note-title">{escape(str(view.title))}</h2>'
        f'<p class="tl-note-sample">{escape(str(view.sample))}</p>'
        "</header>"
    )


def _closing_html(view: ReviewView) -> str:
    """Region 4 then region 5: the rail once, then limitation and actions."""
    parts = [render_evidence_rail(view.evidence)]
    if view.evidence.limitation:
        parts.append(
            f'<p class="tl-note-limitation">{escape(str(view.evidence.limitation))}</p>'
        )
    if view.actions:
        items = "".join(f"<li>{escape(str(a))}</li>" for a in view.actions)
        parts.append(
            '<section class="tl-note-actions">'
            '<h3 class="tl-note-actions-title">Next review action</h3>'
            f"<ul>{items}</ul></section>"
        )
    if view.evidence_used:
        parts.append(render_evidence_disclosure(view.evidence_used))
    return "".join(parts)


def build_note_regions(view: ReviewView) -> str:
    """The note's chrome, in reading order, as one string.

    Pure and complete enough to assert the region invariants on — chiefly
    that the Evidence Rail appears exactly once per note rather than under
    every finding, which is what §7.2 asks for and what four stacked rails
    were doing instead.
    """
    return _head_html(view) + _closing_html(view)


# ---------------------------------------------------------------------------
# The only Streamlit-touching entry point.
# ---------------------------------------------------------------------------


def render_review_reader(st, view: ReviewView, *, state_key: str) -> None:
    """Render one review: header, thesis, one section at a time, then chrome.

    `st` is passed in rather than imported so the module above this line stays
    importable — and testable — without booting Streamlit.
    """
    sections = tuple(view.document.sections)
    total = len(sections)

    with st.container(key="tl_note_sheet"):
        st.markdown(_head_html(view), unsafe_allow_html=True)

        # Region 2. Generated prose, so it takes the safe Markdown path.
        if view.thesis_md:
            st.markdown(
                '<p class="tl-note-thesis-label tl-visually-hidden">'
                "Primary conclusion</p>",
                unsafe_allow_html=True,
            )
            with st.container(key="tl_note_thesis"):
                st.markdown(_md_safe(view.thesis_md))

        if total:
            show_all = st.toggle(
                "Read full note",
                key=f"{state_key}_full",
                help="Show every section of this review at once.",
            )
            if show_all:
                for section in sections:
                    st.markdown(
                        f'<h3 class="tl-note-section-title">'
                        f"{escape(str(section.title))}</h3>",
                        unsafe_allow_html=True,
                    )
                    st.markdown(_md_safe(section.body_md))
            else:
                # One narrow index beside one readable column on a desktop;
                # Streamlit stacks these below its own breakpoint, which is
                # exactly the phone behaviour the spec asks for — a selector
                # above the content, no sticky offscreen panel.
                index_col, body_col = st.columns([1, 3])
                stored = clamp_section(
                    index=st.session_state.get(state_key, 0), total=total
                )
                with index_col:
                    picked = st.radio(
                        "Section",
                        list(range(total)),
                        index=stored,
                        format_func=lambda i: sections[i].title,
                        key=f"{state_key}_pick",
                        label_visibility="collapsed",
                    )
                active = clamp_section(index=picked or 0, total=total)
                st.session_state[state_key] = active
                with body_col:
                    section = sections[active]
                    # Keyed on the section, so Streamlit remounts the container
                    # when the reader moves and the CSS transition replays.
                    # Nothing animates on first load or regeneration.
                    with st.container(key=f"tl_note_section_{section.id}"):
                        st.markdown(
                            f'<h3 class="tl-note-section-title">'
                            f"{escape(str(section.title))}</h3>",
                            unsafe_allow_html=True,
                        )
                        st.markdown(_md_safe(section.body_md))

        st.markdown(_closing_html(view), unsafe_allow_html=True)


def _md_safe(text: str) -> str:
    """Escape `$` so paired dollar amounts are not parsed as LaTeX math.

    Streamlit's Markdown renders `$1,000 ... $500` as a math span and garbles
    the money in between. Same rule the page has always applied; it lives here
    now so every lens gets it rather than only the two that remembered.
    """
    return str(text).replace("\\$", "$").replace("$", "\\$")
