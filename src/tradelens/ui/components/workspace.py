"""Shared presentation primitives for the premium TradeLens workspace.

These are the pieces every redesigned destination composes from: the page
masthead, the ruled KPI strip, the **Evidence Rail**, the numbered research
finding, the editorial readout, and the filter summary.

Design contracts (mirrors ``components/ui.py`` and ``design_system.py``):

- **Pure.** Every function returns an HTML string and this module never
  imports Streamlit, so the primitives are unit-testable without a runtime.
- **Escaped.** Every caller-supplied string goes through ``html.escape``.
  Trade notes, setup names, and AI prose are all user- or model-controlled.
- **One root.** Each renderer emits exactly one root element. Streamlit's
  markdown pass re-parents stray siblings, which silently breaks layouts.
- **Unstyled here.** These builders carry class names only; all styling
  lives in ``design_system.py`` so tokens stay the single source of truth.
- **Formatting-free.** Values arrive pre-formatted as strings. Currency,
  dates, and R-multiples are formatted by the caller that owns the data, so
  one presentation helper never quietly re-rounds a number.

Why the Evidence Rail is a rail, not a card: it is a *margin annotation* —
the thing that lets a trader judge whether an observation deserves weight.
Rendering it as another rounded, filled box would make it compete with the
data it annotates and turn every page back into a wall of cards. It is a
neutral hairline rule, indented content, and mono metadata: the typographic
form scholarly notes have used for centuries, and the one element that
appears on every destination.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Literal, Sequence

MetricTone = Literal["neutral", "positive", "negative", "warning"]
ConfidenceLevel = Literal["low", "medium", "high"]

_TONES: frozenset[str] = frozenset({"neutral", "positive", "negative", "warning"})
_CONFIDENCE_LEVELS: frozenset[str] = frozenset({"low", "medium", "high"})

# Spoken equivalents for the tone a KPI cell carries in colour. A screen
# reader announces text, not `data-tone`, so without these a negative net
# P&L and a positive one read out identically. "neutral" says nothing
# because there is nothing to say — silence is the correct announcement,
# not the word "neutral" injected before every unremarkable figure.
_TONE_ANNOUNCEMENTS: dict[str, str] = {
    "positive": "Up",
    "negative": "Down",
    "warning": "Needs attention",
    "neutral": "",
}


@dataclass(frozen=True)
class MetricItem:
    """One cell of the ruled KPI strip. ``value`` is already formatted."""

    label: str
    value: str
    detail: str | None = None
    tone: MetricTone = "neutral"


@dataclass(frozen=True)
class EvidenceItem:
    """What a trader needs to judge an observation.

    ``limitation`` is optional but strongly encouraged: an observation with
    no stated limitation reads as more certain than the sample supports.
    """

    evidence: str
    sample: str
    confidence: ConfidenceLevel
    limitation: str | None = None


@dataclass(frozen=True)
class ResearchFinding:
    """One numbered finding in a research note. ``number`` is 1-indexed."""

    number: int
    title: str
    body: str
    evidence: EvidenceItem


def _tone(value: object) -> str:
    """Clamp to a known tone. Render paths never raise — an unknown tone
    from stored data must degrade, not blank the page."""
    text = str(value)
    return text if text in _TONES else "neutral"


def _confidence(value: object) -> str:
    """Clamp to a known confidence level, defaulting to the *lowest*.

    Defaulting downward is deliberate: an unrecognised level must never be
    presented as more certain than it is.
    """
    text = str(value)
    return text if text in _CONFIDENCE_LEVELS else "low"


def render_workspace_header(
    title: str,
    subtitle: str,
    eyebrow: str | None = None,
    meta: str | None = None,
) -> str:
    """Page masthead: what this page is, and the scope it is showing.

    ``eyebrow`` carries context that qualifies the whole page (active
    strategy, demo data). ``meta`` carries the scope on the trailing edge
    (date range, account). Both are omitted entirely when absent — an empty
    element still occupies space and breaks the baseline.
    """
    parts = ['<header class="tl-masthead"><div class="tl-masthead-lede">']
    if eyebrow:
        parts.append(f'<p class="tl-masthead-eyebrow">{escape(str(eyebrow))}</p>')
    parts.append(f'<h1 class="tl-masthead-title">{escape(str(title))}</h1>')
    parts.append(f'<p class="tl-masthead-subtitle">{escape(str(subtitle))}</p>')
    parts.append("</div>")
    if meta:
        parts.append(f'<p class="tl-masthead-meta">{escape(str(meta))}</p>')
    parts.append("</header>")
    return "".join(parts)


def render_kpi_strip(items: Sequence[MetricItem]) -> str:
    """One ruled strip of headline numbers — not a row of separate cards.

    Cells are divided by hairlines rather than boxed individually, so the
    figures read as one measurement across a period instead of six competing
    tiles.

    Tone reaches every reader three ways: the colour of the figure, and —
    for anyone who cannot use colour — a visually hidden word inside the
    cell that a screen reader announces before the number. ``data-tone``
    is present for styling and tests, but it carries no meaning to
    assistive technology and is never the only cue.
    """
    cells = []
    for item in items:
        tone = _tone(item.tone)
        announcement = _TONE_ANNOUNCEMENTS[tone]
        spoken = (
            f'<span class="tl-visually-hidden">{announcement}: </span>'
            if announcement
            else ""
        )
        detail = (
            f'<p class="tl-kpi-detail">{escape(str(item.detail))}</p>'
            if item.detail
            else ""
        )
        cells.append(
            f'<div class="tl-kpi-cell tone-{tone}" data-tone="{tone}">'
            f'<p class="tl-kpi-key">{escape(str(item.label))}</p>'
            f'<p class="tl-kpi-figure">{spoken}{escape(str(item.value))}</p>'
            f"{detail}</div>"
        )
    return f'<div class="tl-kpi-strip">{"".join(cells)}</div>'


def render_evidence_rail(item: EvidenceItem) -> str:
    """The signature component: a margin annotation carrying the evidence,
    sample, confidence, and limitation behind one observation.

    Rendered as a definition list so assistive technology announces each
    label with its value rather than reading a run of loose text.
    """
    level = _confidence(item.confidence)
    facts = [
        '<div class="tl-evidence-fact">'
        "<dt>Sample</dt>"
        f'<dd class="tl-evidence-sample">{escape(str(item.sample))}</dd>'
        "</div>",
        '<div class="tl-evidence-fact">'
        "<dt>Confidence</dt>"
        f'<dd class="tl-evidence-confidence conf-{level}">{level.capitalize()}</dd>'
        "</div>",
    ]
    if item.limitation:
        facts.append(
            '<div class="tl-evidence-fact">'
            "<dt>Limitation</dt>"
            f"<dd>{escape(str(item.limitation))}</dd>"
            "</div>"
        )
    return (
        '<aside class="tl-evidence-rail">'
        '<p class="tl-evidence-label">Evidence</p>'
        f'<p class="tl-evidence-claim">{escape(str(item.evidence))}</p>'
        f'<dl class="tl-evidence-facts">{"".join(facts)}</dl>'
        "</aside>"
    )


def render_research_finding(item: ResearchFinding) -> str:
    """One numbered finding of an AI review.

    Findings are numbered because they are a real reading sequence — the
    strongest supported observation first — not to decorate the page.
    """
    return (
        '<article class="tl-finding">'
        f'<p class="tl-finding-number">{item.number:02d}</p>'
        '<div class="tl-finding-body">'
        f'<h3 class="tl-finding-title">{escape(str(item.title))}</h3>'
        f'<p class="tl-finding-text">{escape(str(item.body))}</p>'
        f"{render_evidence_rail(item.evidence)}"
        "</div></article>"
    )


def render_editorial_readout(title: str, body: str, evidence: EvidenceItem) -> str:
    """A short interpretation beneath a chart: what changed, and what the
    evidence does and does not support."""
    return (
        '<section class="tl-readout">'
        f'<h3 class="tl-readout-title">{escape(str(title))}</h3>'
        f'<p class="tl-readout-body">{escape(str(body))}</p>'
        f"{render_evidence_rail(evidence)}"
        "</section>"
    )


def render_filter_summary(items: Sequence[tuple[str, str]]) -> str:
    """The active filters, as a compact line rather than a second control
    panel. With nothing filtered it says so plainly instead of rendering an
    empty strip the reader has to interpret."""
    if not items:
        return (
            '<div class="tl-filter-summary">'
            '<span class="tl-filter-empty">All trades</span></div>'
        )
    chips = "".join(
        '<span class="tl-filter-chip">'
        f'<span class="tl-filter-key">{escape(str(key))}</span>'
        f'<span class="tl-filter-value">{escape(str(value))}</span>'
        "</span>"
        for key, value in items
    )
    return f'<div class="tl-filter-summary">{chips}</div>'


def render_section_header(title: str, subtitle: str | None = None) -> str:
    """Section break within a page.

    Canonical builder: ``design_system.render_section_header`` and
    ``components/ui.section_header`` both delegate here so one header cannot
    drift into three near-identical copies.
    """
    sub = (
        f'<div class="tl-section-subtitle">{escape(str(subtitle))}</div>'
        if subtitle
        else ""
    )
    return (
        '<div class="tl-section-header">'
        f'<h2 class="tl-section-title">{escape(str(title))}</h2>'
        f"{sub}</div>"
    )
