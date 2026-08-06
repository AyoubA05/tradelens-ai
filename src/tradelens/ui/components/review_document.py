"""A pure document model for AI-generated review Markdown.

Standard library only. No Streamlit, no HTML, no model, no database — this
decides where a long note's sections begin and ends there. Rendering,
sanitising, and safety belong to the caller, which keeps this testable without
a browser and keeps the model-output path unchanged.

It never rewrites what the model produced: every section keeps its original
Markdown, so `Read full note` can always render the complete response. A parser
that dropped content would silently discard a trader's review.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Tuple

_HEADING = re.compile(r"^(#{2,3})\s+(.*\S)\s*$")
# The marker character and its run length are both captured. A fence is closed
# only by a run of the SAME character that is at least as long, which is what
# CommonMark says and what lets a model nest a ``` block inside a ```` one —
# a shape generated reviews really do produce when they quote Markdown.
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
# ATX headings may be closed by their own hashes: `## Findings ##` is a
# heading titled "Findings". Left in, the title renders with the hashes.
_ATX_CLOSE = re.compile(r"\s+#+\s*$")


@dataclass(frozen=True)
class ReviewSection:
    """One `##`/`###` section, with its Markdown exactly as generated."""

    id: str
    level: int
    title: str
    body_md: str


@dataclass(frozen=True)
class ReviewDocument:
    """Prose before the first heading, then the sections in reading order."""

    intro_md: str
    sections: Tuple[ReviewSection, ...]

    @property
    def is_empty(self) -> bool:
        return not self.intro_md.strip() and not self.sections


def _slug(title: str, taken: set) -> str:
    """A deterministic, genuinely unique id.

    Deterministic matters: the id survives a rerun, so the reader's selected
    section is still selected after an unrelated widget change.

    Uniqueness is checked against the ids actually issued, not against a count
    per base. Counting collides: "Risk 2" claims `risk-2`, and then a second
    "Risk" — numbered independently — claims `risk-2` as well. Two sections
    with one id means selecting one opens the other.
    """
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "section"
    candidate = base
    n = 1
    while candidate in taken:
        n += 1
        candidate = f"{base}-{n}"
    taken.add(candidate)
    return candidate


def parse_review_markdown(content_md: object) -> ReviewDocument:
    """Split generated Markdown into an intro and its sections.

    Non-string input degrades to an empty document rather than raising: this
    runs inside a render path, where an exception blanks the page.
    """
    if not isinstance(content_md, str) or not content_md.strip():
        return ReviewDocument(intro_md="", sections=())

    intro: list = []
    sections: list = []
    current: dict | None = None
    taken: set = set()
    fence: str | None = None  # the open fence's marker run, e.g. "```"

    for line in content_md.splitlines(keepends=True):
        opener = _FENCE.match(line)
        if opener:
            marker, info = opener.group(1), opener.group(2)
            if fence is None:
                fence = marker
            elif (
                marker[0] == fence[0] and len(marker) >= len(fence) and not info.strip()
            ):
                # A closing fence carries no info string and is at least as
                # long as the one it closes.
                fence = None
            (current["body"] if current else intro).append(line)
            continue

        heading = None if fence else _HEADING.match(line.rstrip("\n"))
        if heading:
            if current:
                sections.append(current)
            title = _ATX_CLOSE.sub("", heading.group(2)).strip() or heading.group(2)
            current = {
                "id": _slug(title, taken),
                "level": len(heading.group(1)),
                "title": title,
                "body": [],
            }
            continue

        (current["body"] if current else intro).append(line)

    if current:
        sections.append(current)

    intro_md = "".join(intro).strip()

    if not sections:
        # No headings at all: one fallback section carrying everything, so the
        # reader has something to select and nothing is lost.
        return ReviewDocument(
            intro_md="",
            sections=(
                ReviewSection(id="note", level=2, title="Review", body_md=intro_md),
            ),
        )

    return ReviewDocument(
        intro_md=intro_md,
        sections=tuple(
            ReviewSection(
                id=s["id"],
                level=s["level"],
                title=s["title"],
                body_md="".join(s["body"]).strip(),
            )
            for s in sections
        ),
    )
