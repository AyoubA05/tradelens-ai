"""Streamlit rendering for the shared low-data policy.

The policy itself moved to `services/sample_policy` so the API and the
Streamlit app decide identically what a sample has earned the right to
display. Only the render helper lives here, because only it touches Streamlit.
"""

from __future__ import annotations

from src.tradelens.services.sample_policy import (  # noqa: F401 — re-exported
    MIN_DATED_POINTS,
    LeadingCategory,
    SampleState,
    enough_categories,
    has_variation,
    leading_category,
    sample_state,
    show_dated_instrument,
    trades_needed,
)


def render_data_state(title: str, body: str, icon: str = "insights") -> None:
    """Render the shared low-data explanation in place of a chart.

    Deliberately compact: an explanation should not occupy the canvas the
    withheld chart would have.
    """
    import streamlit as st

    from src.tradelens.ui.design_system import render_empty_state

    st.markdown(
        f'<div class="tl-data-state">{render_empty_state(icon, title, body)}</div>',
        unsafe_allow_html=True,
    )
