"""Shared forward-looking lexical guard for generated reflection prose.

Moved from `services/trade_summary.py` (Phase 10A, Task A1, decision R7) so the
trade summary, weekly recap and daily debrief share one rule.

This is **lexical defense-in-depth, not a semantic guarantee** (decision C4):
it catches wording that reads as a trade idea; it cannot prove a text is free
of one. The prompts and the product's reflection-only framing remain the
primary control.

Streamlit-free.
"""

from __future__ import annotations

import re

# A structurally perfect answer can still contain a trade idea, which is the one
# thing this product must never emit. These patterns target forward-looking
# directives about a future position; ordinary past-tense reflection ("long
# entries were late", "next time I will size smaller") must pass untouched.
_DIRECTION = (
    r"(?:buy|buys|buying|sell|sells|selling|long|longs|short|shorts|shorting|enter)"
)
# Excludes SMC vocabulary and adjectival uses that describe already-taken trades.
_NOT_A_POSITION = (
    r"(?![-\s]?(?:side|term)\b)"
    r"(?!\s+(?:entry|entries|trade|trades|setup|setups|position|positions|bias|"
    r"execution|executions|sizing|management|liquidity|leg|legs)\b)"
)
_RECOMMENDS = (
    r"(?:you should|you must|you ought to|you need to|you could|we recommend|"
    r"i recommend|i'd recommend|i would recommend|my recommendation is to|"
    r"consider|look to|looking to|aim to|plan to|be ready to|prepare to|"
    r"get ready to|wait to)"
)
_FUTURE = (
    r"(?:next session|next sessions|next trading session|next trading day|"
    r"next week|next open|tomorrow|going forward|upcoming session|"
    r"the coming session)"
)
_LEVEL = r"(?:above|below|near|around|at|from|into|over|under)\s+\$?\d"
# Past-tense reflection markers. Only relax the price-level rule, which is the
# one pattern a genuine retrospective ("entries above 20150 were late") can trip.
_REFLECTIVE = (
    r"\b(?:was|were|had|did|didn't|has been|have been|should have|could have|"
    r"would have|last week|this week|yesterday|previously|already|"
    r"next time)\b"
)

_ADVICE_PATTERNS = (
    # "you should buy", "consider longs", "look to short"
    re.compile(
        rf"\b{_RECOMMENDS}\s+(?:a|an|the|to|going)?\s*\b{_DIRECTION}\b{_NOT_A_POSITION}"
    ),
    # "next session, short the open" — a future marker governing a position
    re.compile(rf"\b{_FUTURE}\b[^.!?]{{0,60}}?\b{_DIRECTION}\b{_NOT_A_POSITION}"),
    re.compile(rf"\b{_DIRECTION}\b{_NOT_A_POSITION}[^.!?]{{0,60}}?\b{_FUTURE}\b"),
)
_PRICE_PATTERNS = (
    # "buy above 20150", "short below 4500"
    re.compile(rf"\b{_DIRECTION}\b{_NOT_A_POSITION}[^.!?]{{0,40}}?\b{_LEVEL}"),
)


def reject_forward_looking(markdown: str, error_cls: type) -> None:
    """Lexical defense-in-depth: refuse text that reads as a trade idea.

    Not a semantic guarantee. Past-tense and process reflection pass. Raises
    `error_cls` with a fixed message on the first offending sentence.
    """
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", markdown.lower()):
        if any(pattern.search(sentence) for pattern in _ADVICE_PATTERNS):
            raise error_cls("The AI review contained forward-looking trade guidance.")
        if re.search(_REFLECTIVE, sentence):
            continue
        if any(pattern.search(sentence) for pattern in _PRICE_PATTERNS):
            raise error_cls("The AI review contained forward-looking trade guidance.")
