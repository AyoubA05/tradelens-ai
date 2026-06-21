"""
Sidebar brand block for TradeLens AI (Week 6 — Ship Week).

Renders a wordmark, the active Strategy Profile name, how many corrections the
AI has learned, and current-week P&L. This is a RENDER-ONLY component: it calls
services for every value and contains no DB queries or business logic.
"""

from __future__ import annotations

import pandas as pd

from src.tradelens.services.corrections import count_corrections
from src.tradelens.services.metrics import current_week_pnl
from src.tradelens.services.strategy import get_active_strategy
from src.tradelens.ui.components.theme import (
    MONO_FONT,
    TEAL,
    TERRA,
    TEXT_MUTED,
    TEXT_SECONDARY,
)

_WORDMARK_SVG = (
    '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" '
    f'stroke="{TEAL}" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round" style="vertical-align:middle">'
    '<path d="M3 17 l5 -6 l4 3 l6 -8"/><path d="M3 21 h18"/></svg>'
)


def _wordmark() -> str:
    return (
        '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">'
        f"{_WORDMARK_SVG}"
        "<span style=\"font-family:'Space Grotesk',sans-serif;font-weight:700;"
        'font-size:1.15rem;letter-spacing:-0.01em">TradeLens AI</span></div>'
    )


def _row(label: str, value: str, value_color: str = TEXT_SECONDARY) -> str:
    return (
        '<div style="display:flex;justify-content:space-between;'
        'align-items:baseline;margin:4px 0">'
        f'<span style="color:{TEXT_MUTED};font-size:0.78rem">{label}</span>'
        f"<span style=\"font-family:'{MONO_FONT}',monospace;font-size:0.82rem;"
        f'color:{value_color}">{value}</span></div>'
    )


def render_sidebar(df: "pd.DataFrame | None" = None, today=None) -> None:
    """Render the brand block in the sidebar. `df` is the already-loaded trades
    frame (passed in so the component performs no data access of its own)."""
    import streamlit as st

    strategy = get_active_strategy()
    strategy_name = (strategy or {}).get("name") or "No active profile"
    corrections = count_corrections()
    week_pnl = current_week_pnl(df, today=today) if df is not None else 0.0

    plural = "" if corrections == 1 else "s"
    pnl_color = TEAL if week_pnl >= 0 else TERRA
    pnl_str = f"${week_pnl:,.2f}"

    block = (
        '<div style="padding:12px 14px;background:rgba(255,255,255,0.04);'
        "border:1px solid rgba(255,255,255,0.10);border-radius:12px;"
        'margin-bottom:12px">'
        f"{_wordmark()}"
        f"{_row('Strategy', strategy_name)}"
        f"{_row('Corrections learned', str(corrections))}"
        f"{_row('This week', pnl_str, pnl_color)}"
        "</div>"
        f'<div style="color:{TEXT_MUTED};font-size:0.72rem;margin-bottom:8px">'
        f"AI has learned {corrections} correction{plural} from you.</div>"
    )
    st.markdown(block, unsafe_allow_html=True)
