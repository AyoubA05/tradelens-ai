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

from src.tradelens.ui.design_system import (
    PLOTLY_TEMPLATE as _DS_PLOTLY_TEMPLATE,
    TL_GRADE_A as _DS_GRADE_A,
    TL_GRADE_B as _DS_GRADE_B,
    TL_GRADE_C as _DS_GRADE_C,
    TL_GRADE_D as _DS_GRADE_D,
    TL_GRADE_F as _DS_GRADE_F,
)

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

# ── Grade scale: A success-green → F danger-red (design_system ramp;
#    matches the outcome semantics used by charts, tables, and KPIs) ──
_GRADE_A = _DS_GRADE_A
_GRADE_B = _DS_GRADE_B
_GRADE_C = _DS_GRADE_C
_GRADE_D = _DS_GRADE_D
_GRADE_F = _DS_GRADE_F
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
# Now defined in design_system.py (single source of truth, unified teal
# colorway) and registered there as the plotly default. Re-exported here
# so existing `from theme import PLOTLY_TEMPLATE` call sites keep working.
PLOTLY_TEMPLATE = _DS_PLOTLY_TEMPLATE


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
    transition: transform 0.15s ease-out, box-shadow 0.15s ease-out, background 0.15s ease-out;
}}
@media (hover: hover) and (pointer: fine) {{
    .stButton > button:hover {{
        background: {TEAL_HOVER};
        box-shadow: 0 0 16px {TEAL_SOFT};
        transform: translateY(-1px);
    }}
}}
.stButton > button:focus-visible {{
    outline: 2px solid {TEAL};
    outline-offset: 2px;
}}
/* .tl-kpi-* and .tl-section-* rules moved to design_system.py (Phase 9
   dedupe) — design_system is injected after theme on every page that
   renders those classes, so it is the single source of truth. */
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
.tl-chat-user {{
    background: {TEAL_SOFT};
    border: 1px solid rgba(32,128,141,0.35);
    border-radius: {RADIUS_MD};
    padding: 10px 14px;
    margin: 6px 0 6px 12%;
}}
.tl-chat-ai {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD};
    padding: 10px 14px;
    margin: 6px 12% 6px 0;
}}
@media (prefers-reduced-motion: reduce) {{
    .stButton > button {{
        transition: none;
    }}
    .stButton > button:hover {{
        transform: none;
    }}
}}
</style>"""


def inject_css() -> None:
    """Inject the global stylesheet. Call once at the top of every page."""
    import streamlit as st  # local import keeps this module streamlit-light

    st.markdown(_build_css(), unsafe_allow_html=True)
