"""Source- and CSS-inspection helpers shared across the dark-workspace tests.

Structural assertions against source are a blunt instrument, and they are used
deliberately: several rules in this phase (no hover-gated layout, one usage log,
no cache clear before regeneration) are properties of *where* code sits, which
no runtime assertion can observe.

Every function returns a value rather than raising when its target is absent,
so a caller fails on the assertion it wrote instead of on a lookup error.
"""

from __future__ import annotations

import re

_DEF = re.compile(r"^(?:async\s+)?def\s+(\w+)\s*\(", re.M)


def near(source: str, anchor: str, radius: int = 400) -> str:
    """The text surrounding the first occurrence of ``anchor``.

    Returns "" when the anchor is absent, so an assertion on the window fails
    on its own terms rather than on an IndexError.
    """
    at = source.find(anchor)
    if at == -1:
        return ""
    return source[max(0, at - radius) : at + radius]


def _block_end(lines: list[str], start: int) -> int:
    """Index of the first line after the block opening at ``start``.

    A top-level block ends at the next line that is non-blank, unindented, and
    not a decorator continuation. Comments at column 0 end it too: a top-level
    comment belongs to whatever follows, not to what preceded it.
    """
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if not line.strip():
            continue
        if line[:1].isspace():
            continue
        return index
    return len(lines)


def function_source(source: str, name: str) -> str:
    """The complete body of a top-level ``def name(...)``, decorators included.

    Returns "" when the function is absent. Nested defs of the same name are
    ignored — only a definition at column 0 counts, because these probes make
    claims about module-level structure.
    """
    lines = source.splitlines(keepends=True)
    for index, line in enumerate(lines):
        match = _DEF.match(line)
        if not match or match.group(1) != name:
            continue
        start = index
        # Walk back over stacked decorators so @property/@staticmethod stay
        # attached to the function they modify.
        while start and lines[start - 1].lstrip().startswith("@"):
            start -= 1
        return "".join(lines[start : _block_end(lines, index)])
    return ""


def outside(source: str, name: str) -> str:
    """``source`` with the complete top-level block ``name`` removed.

    Used to prove a token appears only inside the region licensed to carry it —
    for example that TL_DANGER is referenced only within the Danger Zone
    renderer. ``name`` is a top-level ``def`` name; when it is absent the whole
    source is returned, so the caller's assertion still runs against real text.
    """
    block = function_source(source, name)
    if not block:
        return source
    return source.replace(block, "", 1)


def media_context(css: str, block: str) -> str:
    """The ``@media (...)`` condition ``block`` sits inside, or "".

    Brace-counted rather than "the nearest preceding @media": an earlier media
    query that already closed must not be reported as the enclosing one.
    """
    at = css.find(block)
    if at == -1:
        return ""
    depth = 0
    stack: list[tuple[int, str]] = []
    for match in re.finditer(r"@media([^{]*)\{|\{|\}", css[:at]):
        token = match.group(0)
        if token.startswith("@media"):
            stack.append((depth, match.group(1).strip()))
            depth += 1
        elif token == "{":
            depth += 1
        else:
            depth -= 1
            while stack and stack[-1][0] >= depth:
                stack.pop()
    return stack[-1][1] if stack else ""
