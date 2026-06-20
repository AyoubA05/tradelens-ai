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
) -> str:
    """A glassmorphism KPI card. Value renders in JetBrains Mono; an optional
    delta shows a colored arrow (teal up / terra down)."""
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
    return (
        '<div class="tl-kpi-card">'
        f'<div class="tl-kpi-label">{html.escape(str(label))}</div>'
        f'<div class="tl-kpi-value" style="font-family:\'{MONO_FONT}\',monospace">'
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


def section_header(title: str, subtitle: Optional[str] = None) -> str:
    """A styled section header with an optional muted subtitle."""
    parts = [f'<div class="tl-section-title">{html.escape(str(title))}</div>']
    if subtitle:
        parts.append(
            f'<div class="tl-section-subtitle">{html.escape(str(subtitle))}</div>'
        )
    return f'<div class="tl-section-header">{"".join(parts)}</div>'


def empty_state(
    message: str,
    cta_label: Optional[str] = None,
    cta_href: Optional[str] = None,
) -> str:
    """A designed empty state: glass card, inline-SVG icon, message, optional CTA link."""
    cta = ""
    if cta_label and cta_href:
        cta = (
            f'<a class="tl-empty-cta" href="{html.escape(str(cta_href))}">'
            f"{html.escape(str(cta_label))}</a>"
        )
    return (
        '<div class="tl-empty-state">'
        f'<div class="tl-empty-icon">{_EMPTY_ICON}</div>'
        f'<div class="tl-empty-message">{html.escape(str(message))}</div>'
        f"{cta}</div>"
    )
