"""
Design-system foundation for TradeLens AI (Week 6 — Ship Week).

ONE source of truth for visual tokens (color, type scale, radii, fonts), a
Plotly template, and the global CSS injector. Pages and components import from
here — never redefine colors locally.

Design direction: dark-only, futuristic "trading performance lab", unified with
the marketing site (SP4): background/teal come from design_system tokens,
Schibsted Grotesk headings, JetBrains Mono for all numerals, Satoshi body.
TERRA (#A84B2F) remains as a distinct legacy callout semantic.

R1 RULE (enforced by tests): inject_css() must only target SCOPED selectors
([data-testid="..."], .stMetric, .stSidebar, .stButton > button,
.element-container, and our own .tl-* classes). Never style bare HTML element
tags (p, div, input, button, ...) — that breaks Streamlit widgets and contrast.
"""

from __future__ import annotations

from src.tradelens.ui.design_system import (
    PLOTLY_TEMPLATE as _DS_PLOTLY_TEMPLATE,
    TL_ACCENT_ACTION as _DS_ACTION,
    TL_PRIMARY_HOVER as _DS_ACTION_HOVER,
    TL_PRIMARY_DIM as _DS_ACTION_WASH,
    TL_SURFACE_CANVAS as _DS_CANVAS,
    TL_SURFACE_CHART as _DS_CHART_STAGE,
    TL_FOCUS as _DS_FOCUS,
    TL_GRADE_A as _DS_GRADE_A,
    TL_GRADE_B as _DS_GRADE_B,
    TL_GRADE_C as _DS_GRADE_C,
    TL_GRADE_D as _DS_GRADE_D,
    TL_GRADE_F as _DS_GRADE_F,
    TL_LINE_HAIRLINE as _DS_HAIRLINE,
    TL_CONTENT_PRIMARY as _DS_INK,
    TL_SURFACE_ELEVATED as _DS_MIST,
    TL_CONTENT_SECONDARY as _DS_MUTED,
    TL_SURFACE_PANEL as _DS_PAPER,
    TL_PRIMARY as _DS_PRIMARY,
    TL_PRIMARY_DIM as _DS_PRIMARY_DIM,
    TL_PRIMARY_HOVER as _DS_PRIMARY_HOVER,
    TL_SURFACE_RAIL as _DS_RAIL,
)

# ── Compatibility re-exports for call sites that import from here ──────────
# These names date from the hybrid theme and are kept so existing imports keep
# working while the pages are migrated. They now resolve to the one dark role
# system in design_system.py, so PAPER is a dark panel and INK is light text —
# the names no longer describe their values. Task 2 retires them.
CANVAS = _DS_CANVAS
PAPER = _DS_PAPER
MIST = _DS_MIST
INK = _DS_INK
HAIRLINE = _DS_HAIRLINE
ACTION = _DS_ACTION
ACTION_HOVER = _DS_ACTION_HOVER
ACTION_WASH = _DS_ACTION_WASH
RAIL = _DS_RAIL
CHART_STAGE = _DS_CHART_STAGE
FOCUS = _DS_FOCUS

# ── Surfaces ──────────────────────────────────────────────────────
# These names drive theme.py's own CSS (.tl-empty-state, .tl-chat-*,
# .tl-grade-chip) and are imported directly by ui.py and demo_banner.py.
# They follow the LIGHT workspace: left on the pre-redesign dark values, a
# 6%-white surface would paint white-on-white once the canvas turned light.
BG = _DS_CANVAS
SURFACE = _DS_PAPER
SURFACE_HOVER = _DS_MIST
BORDER = _DS_HAIRLINE

# ── Brand ─────────────────────────────────────────────────────────
TEAL = _DS_PRIMARY
TEAL_HOVER = _DS_PRIMARY_HOVER
TEAL_SOFT = _DS_PRIMARY_DIM
# TERRA is a distinct legacy semantic (ui.py callout border), not a competing
# brand color — intentionally retained.
TERRA = "#A84B2F"
TERRA_SOFT = "rgba(168,75,47,0.15)"

# ── Text hierarchy ────────────────────────────────────────────────
# Two levels on light surfaces, per spec 8: ink for what is read, muted for
# what qualifies it. SECONDARY and MUTED collapse onto the same role — the
# third level existed only to separate two greys on a dark background.
TEXT_PRIMARY = _DS_INK
TEXT_SECONDARY = _DS_MUTED
TEXT_MUTED = _DS_MUTED

# ── Radii ─────────────────────────────────────────────────────────
# 6px controls, 8px panels, 10px overlays (spec 8) — the universal 16px
# card radius is retired.
RADIUS_SM = "6px"
RADIUS_MD = "8px"
RADIUS_LG = "10px"

# ── Fonts ─────────────────────────────────────────────────────────
# SP4: matches the marketing site (site/index.html) so site -> app is one brand.
HEADING_FONT = "Schibsted Grotesk"
MONO_FONT = "JetBrains Mono"
BODY_FONT = "Satoshi"

# Satoshi is Fontshare-hosted; the rest are Google. Two stylesheet imports.
_FONT_IMPORT = (
    "https://fonts.googleapis.com/css2?"
    "family=Schibsted+Grotesk:wght@500;600;700&"
    "family=JetBrains+Mono:wght@400;500;600&display=swap"
)
_FONT_IMPORT_FONTSHARE = (
    "https://api.fontshare.com/v2/css?f[]=satoshi@400,500,700&display=swap"
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
@import url('{_FONT_IMPORT_FONTSHARE}');
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
    background: {RAIL};
    border-right: 1px solid {RAIL};
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
/* Deep teal, not the bright instrument teal: this button carries white
   text on a light surface, where #00E5CC measures 1.7:1. No lift and no
   glow — a press must not move the layout under the pointer. */
.stButton > button {{
    background: {ACTION};
    color: {PAPER};
    border: 1px solid {ACTION};
    border-radius: {RADIUS_SM};
    font-weight: 500;
    transition: background 0.16s ease-out;
}}
@media (hover: hover) and (pointer: fine) {{
    .stButton > button:hover {{
        background: {ACTION_HOVER};
    }}
}}
.stButton > button:focus-visible {{
    outline: 2px solid {ACTION};
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
    background: {ACTION_WASH};
    color: {ACTION};
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
    background: {ACTION};
    color: {PAPER};
    border-radius: {RADIUS_SM};
    font-weight: 500;
    text-decoration: none;
}}
.tl-chat-user {{
    background: {ACTION_WASH};
    border: 1px solid {BORDER};
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
}}
</style>"""


def inject_css() -> None:
    """Inject the global stylesheet. Call once at the top of every page."""
    import streamlit as st  # local import keeps this module streamlit-light

    st.markdown(_build_css(), unsafe_allow_html=True)
