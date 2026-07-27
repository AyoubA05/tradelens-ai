"""
Reusable UI component factories for TradeLens AI (Week 6 — Ship Week).

These are PURE string builders — they return HTML and never call streamlit.
Pages render them with `st.markdown(..., unsafe_allow_html=True)`. Keeping them
streamlit-free makes them trivially unit-testable and enforces the rule that all
shared styling lives here, not as page-local one-offs.

No emojis as icons — arrows and the empty-state glyph are inline SVG.
"""

from __future__ import annotations

import html
from typing import Optional

from src.tradelens.ui.components.theme import (
    GRADE_COLORS,
    KILLZONE_LABELS,
    MONO_FONT,
    TEAL,
    TERRA,
    TEXT_MUTED,
)
from src.tradelens.ui.components.workspace import render_section_header

_ARROW_UP = (
    '<svg width="10" height="10" viewBox="0 0 10 10" style="vertical-align:middle">'
    '<path d="M5 1 L9 8 L1 8 Z" fill="currentColor"/></svg>'
)
_ARROW_DOWN = (
    '<svg width="10" height="10" viewBox="0 0 10 10" style="vertical-align:middle">'
    '<path d="M5 9 L1 2 L9 2 Z" fill="currentColor"/></svg>'
)
_EMPTY_ICON = (
    '<svg width="40" height="40" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="1.5" stroke-linecap="round" '
    'stroke-linejoin="round">'
    '<rect x="3" y="4" width="18" height="16" rx="2"/>'
    '<path d="M7 14 l3 -3 l3 3 l4 -5"/></svg>'
)


def kpi_card(
    label: str,
    value: str,
    delta: Optional[str] = None,
    delta_positive: Optional[bool] = None,
    tooltip: Optional[str] = None,
    value_color: Optional[str] = None,
) -> str:
    """A glassmorphism KPI card. Value renders in JetBrains Mono; an optional
    delta shows a colored arrow (teal up / terra down).

    `tooltip` adds a native hover title on the value (e.g. "No losses yet" for an
    infinite profit factor). `value_color` tints the value (teal wins / terra
    losses) without affecting the label.
    """
    delta_html = ""
    if delta is not None:
        positive = delta_positive
        if positive is None:
            positive = not str(delta).strip().startswith("-")
        color = TEAL if positive else TERRA
        arrow = _ARROW_UP if positive else _ARROW_DOWN
        delta_html = (
            f'<div class="tl-kpi-delta" style="color:{color}">'
            f"{arrow} {html.escape(str(delta))}</div>"
        )
    title_attr = f' title="{html.escape(str(tooltip))}"' if tooltip else ""
    color_style = f";color:{value_color}" if value_color else ""
    return (
        '<div class="tl-kpi-card">'
        f'<div class="tl-kpi-label">{html.escape(str(label))}</div>'
        f'<div class="tl-kpi-value"{title_attr} '
        f"style=\"font-family:'{MONO_FONT}',monospace{color_style}\">"
        f"{html.escape(str(value))}</div>"
        f"{delta_html}"
        "</div>"
    )


def grade_chip(grade: Optional[str]) -> str:
    """A pill chip colored on the A-tier-teal → F-terra scale."""
    g = str(grade).strip() if grade else ""
    color = GRADE_COLORS.get(g, TEXT_MUTED)
    label = html.escape(g) if g else "—"
    return (
        f'<span class="tl-grade-chip" style="color:{color};border-color:{color}">'
        f"{label}</span>"
    )


def killzone_badge(killzone: Optional[str]) -> str:
    """A subtle badge with a human-readable killzone label. Empty in → empty out."""
    if not killzone:
        return ""
    key = str(killzone).strip().lower()
    label = KILLZONE_LABELS.get(key, key.replace("_", " ").title())
    return f'<span class="tl-killzone-badge">{html.escape(label)}</span>'


def error_box(message: str) -> str:
    """Persistent inline error block. Escapes the message.

    One shared builder so AI failures render identically everywhere — a lasting,
    readable message rather than a transient toast/warning.

    Styling lives in the design system (``.tl-error-box``) rather than inline:
    the copy used to be a literal ``#e0855f``, a light terracotta chosen for a
    dark surface, which measured 2.2:1 once the workspace turned light. The
    message a trader needs when something failed is the last text that should
    be hard to read.
    """
    return f'<div class="tl-error-box" role="alert">{html.escape(str(message))}</div>'


def section_header(title: str, subtitle: Optional[str] = None) -> str:
    """A styled section header with an optional muted subtitle.

    Delegates to ``components/workspace.py``: this and
    ``design_system.render_section_header`` were byte-identical copies of the
    same markup, which is how one header quietly becomes three.
    """
    return render_section_header(title, subtitle)


def empty_state(
    message: str,
    cta_label: Optional[str] = None,
    cta_href: Optional[str] = None,
    cta2_label: Optional[str] = None,
    cta2_href: Optional[str] = None,
) -> str:
    """A designed empty state: glass card, inline-SVG icon, message, and up to two
    CTA links (primary teal button + an optional secondary text link)."""
    ctas = ""
    if cta_label and cta_href:
        ctas += (
            f'<a class="tl-empty-cta" href="{html.escape(str(cta_href))}" '
            f'target="_self">{html.escape(str(cta_label))}</a>'
        )
    if cta2_label and cta2_href:
        ctas += (
            f'<a href="{html.escape(str(cta2_href))}" target="_self" '
            'style="display:inline-block;margin-left:14px;color:#8E9196;'
            'font-size:0.92rem;text-decoration:none">'
            f"{html.escape(str(cta2_label))} →</a>"
        )
    return (
        '<div class="tl-empty-state">'
        f'<div class="tl-empty-icon">{_EMPTY_ICON}</div>'
        f'<div class="tl-empty-message">{html.escape(str(message))}</div>'
        f"{ctas}</div>"
    )
