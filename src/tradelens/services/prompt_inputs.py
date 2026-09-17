"""The one sanitiser for untrusted text that re-enters a prompt.

Trader-authored text (Strategy Profile fields, journal and process notes) and
model-read text (observations read out of a trader-supplied chart image) are
prompt DATA. Before any of it reaches a model it is bounded to
`MAX_PROMPT_TEXT_CHARS` and stripped of anything markup-shaped, so it cannot
open a fake section, close a fence, or pose as an instruction block.

Every prompt uses these functions — the Phase 5 trade analysis, journal and
grading prompts (through `trade_analysis`, which re-exports them under its
historical private names so fingerprints and tests are unchanged) and the AI
Partner. One definition means one rule; a second copy would drift.

No Streamlit imports here.
"""

from __future__ import annotations

import re

from src.tradelens.services.ai_text_guard import bounded_text

# Same rule `ai_text_guard.fence` applies inside a block.
MARKUP_IN_PROMPT = re.compile(r"[<>]")


def prompt_scalar(value) -> str:
    """One short untrusted value: bounded, and stripped of anything markup-shaped."""
    return MARKUP_IN_PROMPT.sub("", bounded_text(value))


def sanitised_strategy(strategy):
    """Bound every trader-authored Strategy Profile string before prompting."""
    if not isinstance(strategy, dict):
        return strategy
    return {
        key: prompt_scalar(value) if isinstance(value, str) else value
        for key, value in strategy.items()
    }


def sanitised_data(value):
    """Recursively sanitise a JSON-shaped structure bound for a prompt.

    Every string value and every string dict key goes through `prompt_scalar`
    (pattern breakdowns are keyed and labelled by trader-typed values such as
    setup_type or mistake tags). Numbers, bools, None and other scalars are
    returned unchanged; lists and tuples are rebuilt as lists.
    """
    if isinstance(value, str):
        return prompt_scalar(value)
    if isinstance(value, dict):
        return {
            (prompt_scalar(k) if isinstance(k, str) else k): sanitised_data(v)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [sanitised_data(item) for item in value]
    return value
