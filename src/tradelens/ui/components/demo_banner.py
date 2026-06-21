"""
Shared DEMO_MODE banner for TradeLens AI (Week 6 — Ship Week).

Single source of truth: every page calls render_demo_banner() right after
inject_css(). It renders only when demo_mode is on, so it is a no-op in normal
use. Keeps the "Demo data — AI outputs cached, zero API spend" message
consistent across the whole app.
"""

from __future__ import annotations

from src.tradelens.services.demo import is_demo
from src.tradelens.ui.components.theme import TEAL, TEAL_SOFT, TEXT_SECONDARY

_BANNER = (
    f'<div style="background:{TEAL_SOFT};border:1px solid {TEAL};'
    "border-radius:8px;padding:8px 14px;margin-bottom:12px;"
    f'color:{TEXT_SECONDARY};font-size:0.85rem">'
    "<strong>Demo mode</strong> — you're viewing sample data and cached AI "
    "responses. Nothing here is live, and no API calls are made."
    "</div>"
)


def render_demo_banner() -> None:
    """Render the demo banner if DEMO_MODE is on; otherwise do nothing."""
    if not is_demo():
        return
    import streamlit as st

    st.markdown(_BANNER, unsafe_allow_html=True)
