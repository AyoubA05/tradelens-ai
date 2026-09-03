"""Shared prompt-safety helpers for every per-trade AI consumer.

Two directions, both load-bearing:

* **In.** Trade notes, emotions and correction reasons are typed by the
  trader; chart text is read by a model out of an image. All of it is data.
  It is bounded and fenced so its length cannot be used as a lever and so it
  cannot forge the end of the block it sits in. This does not make injection
  impossible; it removes the two cheapest tricks and bounds the rest.
* **Out.** Phase 3E already decided what a post-trade journal may not say and
  encoded it in `trade_summary`. This module re-exports that decision rather
  than restating it: one regex set, one place to fix, no chance of the journal
  and the summary disagreeing about what counts as advice.

No Streamlit imports here.
"""

from __future__ import annotations

import re

from src.tradelens.services.trade_summary import (
    TradeSummaryError,
    _reject_forward_looking,
)

# Same ceiling `trade_summary` applies to a snapshot field. One number.
MAX_PROMPT_TEXT_CHARS = 500

# Anything that could read as markup is stripped from fenced values, so a
# value cannot close its own block or open a new one.
_MARKUP = re.compile(r"[<>]")


class ForwardLookingContent(Exception):
    """Raised when generated text reads as a trade idea, not a reflection."""


def bounded_text(value) -> str:
    """Normalise one untrusted value to a bounded, single-purpose string."""
    return str(value or "").strip()[:MAX_PROMPT_TEXT_CHARS]


def fence(label: str, value) -> str:
    """Wrap one untrusted value in a labelled block it cannot escape.

    Angle brackets are removed from the value before interpolation, so the
    closing tag in the result is always ours. Without this a note reading
    `</trade_notes> SYSTEM: ...` would end the data block early and the rest
    would be read as instructions.
    """
    return f"<{label}>\n{_MARKUP.sub('', bounded_text(value))}\n</{label}>"


def reject_forward_looking(text: str) -> None:
    """Refuse generated text that gives forward-looking trade guidance.

    Delegates to Phase 3E's rule set so there is exactly one definition of
    what this product will not say.
    """
    try:
        _reject_forward_looking(text or "")
    except TradeSummaryError as exc:
        raise ForwardLookingContent(str(exc)) from exc
