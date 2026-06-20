"""
Design-system foundation for TradeLens AI (Week 6 — Ship Week).

ONE source of truth for visual tokens (color, type scale, radii, fonts), a
Plotly template, and the global CSS injector. Pages and components import from
here — never redefine colors locally.

Design direction: dark-only, futuristic "trading performance lab". Background
#0E1117, teal #20808D, terra #A84B2F, muted gray text hierarchy. Space Grotesk
headings, JetBrains Mono for all numerals, Inter body.

R1 RULE (enforced by tests): inject_css() must only target SCOPED selectors
([data-testid="..."], .stMetric, .stSidebar, .stButton > button,
.element-container, and our own .tl-* classes). Never style bare HTML element
tags (p, div, input, button, ...) — that breaks Streamlit widgets and contrast.
"""

from __future__ import annotations

import plotly.graph_objects as go

# ── Surfaces ──────────────────────────────────────────────────────
BG = "#0E1117"
SURFACE = "rgba(255,255,255,0.06)"
SURFACE_HOVER = "rgba(255,255,255,0.09)"
BORDER = "rgba(255,255,255,0.10)"

# ── Brand ─────────────────────────────────────────────────────────
TEAL = "#20808D"
TEAL_HOVER = "#1c727e"
TEAL_SOFT = "rgba(32,128,141,0.15)"
TERRA = "#A84B2F"
TERRA_SOFT = "rgba(168,75,47,0.15)"

# ── Text hierarchy ────────────────────────────────────────────────
TEXT_PRIMARY = "#E8EAED"
TEXT_SECONDARY = "#B4B8BD"
TEXT_MUTED = "#8E9196"

# ── Radii ─────────────────────────────────────────────────────────
RADIUS_SM = "8px"
RADIUS_MD = "12px"
RADIUS_LG = "16px"

# ── Fonts ─────────────────────────────────────────────────────────
HEADING_FONT = "Space Grotesk"
MONO_FONT = "JetBrains Mono"
BODY_FONT = "Inter"

_FONT_IMPORT = (
    "https://fonts.googleapis.com/css2?"
    "family=Space+Grotesk:wght@500;600;700&"
    "family=Inter:wght@400;500;600&"
    "family=JetBrains+Mono:wght@400;500;600&display=swap"
)

# ── Grade scale: A-tier teal → F terra (semantic, not decorative) ──
_GRADE_A = TEAL
_GRADE_B = "#4C9A8A"
_GRADE_C = "#9A8E5C"
_GRADE_D = "#B5613F"
_GRADE_F = TERRA
GRADE_COLORS = {
    "A+": _GRADE_A,
    "A": _GRADE_A,
    "A-": _GRADE_A,
    "B+": _GRADE_B,
    "B": _GRADE_B,
    "B-": _GRADE_B,
    "C+": _GRADE_C,
    "C": _GRADE_C,
    "C-": _GRADE_C,
    "D+": _GRADE_D,
    "D": _GRADE_D,
    "D-": _GRADE_D,
    "F": _GRADE_F,
}

# ── Killzone display labels ───────────────────────────────────────
KILLZONE_LABELS = {
    "asia": "Asia",
    "london": "London",
    "london_open": "London Open",
    "ny_am": "NY AM",
    "ny_pm": "NY PM",
    "ny_lunch": "NY Lunch",
    "london_close": "London Close",
}

# ── Plotly template ───────────────────────────────────────────────
PLOTLY_TEMPLATE = go.layout.Template(
    layout=go.Layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=f"{BODY_FONT}, sans-serif", color=TEXT_PRIMARY),
        colorway=[TEAL, TERRA, _GRADE_B, _GRADE_C, TEXT_MUTED],
        xaxis=dict(gridcolor=BORDER, zerolinecolor=BORDER),
        yaxis=dict(gridcolor=BORDER, zerolinecolor=BORDER),
        hoverlabel=dict(font=dict(family=f"{MONO_FONT}, monospace")),
    )
)


def _build_css() -> str:
    """Return the global stylesheet. Pure (no Streamlit) so it is unit-testable."""
    return f"""<style>
@import url('{_FONT_IMPORT}');

[data-testid="stAppViewContainer"] {{
    font-family: '{BODY_FONT}', sans-serif;
    color: {TEXT_PRIMARY};
}}
[data-testid="stHeader"] {{
    background: transparent;
}}
[data-testid="stAppViewContainer"] h1,
[data-testid="stAppViewContainer"] h2,
[data-testid="stAppViewContainer"] h3 {{
    font-family: '{HEADING_FONT}', sans-serif;
    font-weight: 600;
    letter-spacing: -0.01em;
}}
[data-testid="stSidebar"] {{
    background: {BG};
    border-right: 1px solid {BORDER};
}}
.stMetric [data-testid="stMetricValue"] {{
    font-family: '{MONO_FONT}', monospace;
    font-weight: 600;
    color: {TEXT_PRIMARY};
}}
.stMetric [data-testid="stMetricDelta"] {{
    font-family: '{MONO_FONT}', monospace;
}}
.stMetric [data-testid="stMetricLabel"] {{
    color: {TEXT_MUTED};
}}
.stButton > button {{
    background: {TEAL};
    color: #ffffff;
    border: 1px solid {TEAL};
    border-radius: {RADIUS_SM};
    font-weight: 600;
    transition: transform 0.15s ease, box-shadow 0.15s ease, background 0.15s ease;
}}
.stButton > button:hover {{
    background: {TEAL_HOVER};
    box-shadow: 0 0 16px {TEAL_SOFT};
    transform: translateY(-1px);
}}
.tl-kpi-card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD};
    padding: 18px 20px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.25);
    transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}}
.tl-kpi-card:hover {{
    transform: translateY(-2px);
    border-color: {TEAL};
    box-shadow: 0 0 18px {TEAL_SOFT};
}}
.tl-kpi-label {{
    color: {TEXT_MUTED};
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}}
.tl-kpi-value {{
    font-family: '{MONO_FONT}', monospace;
    font-size: 1.7rem;
    font-weight: 600;
    color: {TEXT_PRIMARY};
}}
.tl-kpi-delta {{
    font-family: '{MONO_FONT}', monospace;
    font-size: 0.85rem;
    margin-top: 2px;
}}
.tl-grade-chip {{
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    border: 1px solid;
    font-family: '{MONO_FONT}', monospace;
    font-weight: 600;
    font-size: 0.8rem;
    background: {SURFACE};
}}
.tl-killzone-badge {{
    display: inline-block;
    padding: 2px 10px;
    border-radius: {RADIUS_SM};
    background: {TEAL_SOFT};
    color: {TEXT_SECONDARY};
    font-size: 0.78rem;
    font-weight: 500;
}}
.tl-section-header {{
    margin: 10px 0 6px 0;
}}
.tl-section-title {{
    font-family: '{HEADING_FONT}', sans-serif;
    font-size: 1.25rem;
    font-weight: 600;
    color: {TEXT_PRIMARY};
}}
.tl-section-subtitle {{
    color: {TEXT_MUTED};
    font-size: 0.9rem;
}}
.tl-empty-state {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_LG};
    padding: 48px 32px;
    text-align: center;
}}
.tl-empty-icon {{
    opacity: 0.7;
    margin-bottom: 12px;
    color: {TEXT_MUTED};
}}
.tl-empty-message {{
    color: {TEXT_SECONDARY};
    font-size: 1rem;
    margin-bottom: 16px;
}}
.tl-empty-cta {{
    display: inline-block;
    padding: 8px 18px;
    background: {TEAL};
    color: #ffffff;
    border-radius: {RADIUS_SM};
    font-weight: 600;
    text-decoration: none;
}}
</style>"""


def inject_css() -> None:
    """Inject the global stylesheet. Call once at the top of every page."""
    import streamlit as st  # local import keeps this module streamlit-light

    st.markdown(_build_css(), unsafe_allow_html=True)
