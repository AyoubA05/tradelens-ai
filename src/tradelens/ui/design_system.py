"""TradeLens AI design system — single source of truth for UI tokens & CSS.

This module supersedes ``components/theme.py`` as the styling source of truth
(PRODUCT.md). Pages inject it AFTER ``theme.inject_css()`` during the
migration window, so on equal-specificity collisions (``.tl-kpi-card`` etc.)
these rules win; duplicated theme.py rules are removed in Phase 9.

Design contracts honored here:
- Helpers are PURE: they return HTML strings and never import Streamlit at
  module level (mirrors ``components/ui.py``). Only ``inject_design_system``
  touches Streamlit, via a lazy import, so this module stays unit-testable.
- Every CSS selector is scoped (starts with ``.``, ``#``, ``[`` or ``:``) —
  never a bare HTML tag — per the R1 rule enforced in tests/test_theme.py.
- Chrome suppression is config-first: ``.streamlit/config.toml`` sets
  ``client.toolbarMode = "minimal"`` (verified for the pinned Streamlit
  1.50.0). No unproven ``data-testid`` selectors are used; the proven set on
  1.50.0 is: stAppViewContainer, stHeader, stSidebar, stMetricValue,
  stMetricDelta, stMetricLabel.
- Insight-card variants use tinted backgrounds + an accent-colored icon,
  NOT colored side borders (owner decision, PRODUCT.md anti-pattern).
- Headings use the body stack (owner decision — no heading font token).
- Red is for errors only; never for checkbox/confirmation states.

Known deviation from the build spec, by necessity: the spec asked
``inject_design_system`` to skip injection when a ``st.session_state`` flag
is set. Streamlit clears all un-rendered elements on every rerun, so a
session-persistent skip-flag would drop the CSS after the first interaction.
Instead the CSS is (re)injected on every script run — exactly how
``theme.inject_css()`` already behaves — and the flag is kept only as a
marker for introspection. Duplicate injection within one run is harmless
(identical ``<style>`` blocks are deterministic).
"""

from __future__ import annotations

import base64
import math
from functools import lru_cache
from html import escape
from pathlib import Path
from typing import Optional

import plotly.graph_objects as go
import plotly.io as pio

from src.tradelens.ui.components.workspace import (
    render_section_header as _render_section_header,
)

# =========================================================================
# COLOR TOKENS — the fixed hybrid theme
# =========================================================================
# The signed-in product runs ONE theme with two surface families. There is
# no toggle; a view is light or dark because of what it does, not because
# of a preference:
#
#   LIGHT WORKSPACE  reading, forms, tables, decisions  (canvas / paper)
#   DARK INSTRUMENTS navigation rail, charts, focused AI reading surfaces
#
# Each family needs its own semantic ramp. Deep teal #087F74 is legible on
# white and invisible on the rail; bright teal #00E5CC is the reverse. So
# the two families are named separately rather than one being redefined —
# charts.py reads TL_SUCCESS/TL_DANGER/TL_WARNING for marks drawn on the
# dark stage, and repointing those at the light forms would put dark green
# on near-black. Every pair below is contrast-tested in
# tests/test_design_system.py, not asserted from the specification.
# -------------------------------------------------------------------------
# LIGHT WORKSPACE
# -------------------------------------------------------------------------
TL_CANVAS = "#F3F6F6"  # mineral workspace background
TL_PAPER = "#FFFFFF"  # forms, tables, readable content
TL_MIST = "#E9EFEF"  # selected rows, filter wells, grouping
TL_INK = "#132125"  # primary text on light surfaces      15.19:1 on canvas
TL_MUTED = "#5B6A70"  # secondary text on light surfaces    5.17:1 on canvas
TL_HAIRLINE = "#D9E2E2"  # structural rules and panel borders
# The specification proposed #087F74. Measured as text on the mineral canvas
# it is 4.496:1 — under the 4.5:1 AA floor by four thousandths. Darkened one
# step so the action reads as a link on canvas as well as a button fill.
TL_ACTION = "#087C71"  # THE primary action on light surfaces
TL_ACTION_HOVER = "#066A61"  # darker, so white label keeps its ratio
# Semantic ramp for light surfaces. Darker than the instrument ramp because
# these sit on white and mineral, not on near-black.
TL_SUCCESS_INK = "#167A47"  # 4.94:1 on canvas
TL_DANGER_INK = "#B53A43"  # 5.29:1 on canvas
# The specification proposed #A76500; measured 4.29:1 on the mineral canvas,
# below the 4.5:1 AA floor for normal text. Darkened one step to clear it.
TL_WARNING_INK = "#9C5F00"  # 4.77:1 on canvas
# Quiet grounds, not text colors. A 10% tint of a hue darkens the surface
# toward that hue's own ink, so semantic-text-on-its-own-tint measures
# 4.1-4.9:1 and cannot be rescued by adjusting the tint — the pattern is
# what fails. The rule instead: semantic hue MARKS and NUMBERS, and never
# tints the text sitting on it. Ink on any wash measures 13-14:1, and the
# hue survives as a dot that clears the 3:1 non-text threshold.
TL_SUCCESS_WASH = "rgba(22,122,71,0.10)"
TL_DANGER_WASH = "rgba(181,58,67,0.10)"
TL_WARNING_WASH = "rgba(156,95,0,0.10)"
TL_ACTION_WASH = "rgba(8,124,113,0.10)"

# -------------------------------------------------------------------------
# DARK INSTRUMENTS
# -------------------------------------------------------------------------
TL_RAIL = "#0F171B"  # navigation rail
TL_CHART_STAGE = "#101A1E"  # chart frames and focused AI reading surfaces
TL_FOCUS = "#00E5CC"  # active marks on dark surfaces (== TL_PRIMARY)

# -------------------------------------------------------------------------
# DARK INSTRUMENT RAMP (pre-redesign palette, values unchanged)
# -------------------------------------------------------------------------
TL_BG = "#0d1117"
TL_SURFACE = "#161b22"
TL_SURFACE_2 = "#1c232b"
TL_BORDER = "#252a32"
TL_BORDER_SUBTLE = "#1e2228"
TL_TEXT = "#e8eaed"
# Muted/faint tuned for WCAG AA (>=4.5:1 small text) against the SP4 site
# surfaces, which are lighter than the pre-SP4 ones:
#   muted  5.65 on BG / 5.17 on SURFACE / 4.73 on SURFACE_2
#   faint  5.50 on BG / 5.03 on SURFACE / 4.61 on SURFACE_2
# faint was #79828f, which fell to 4.08 on the lighter SURFACE_2 (below AA).
TL_TEXT_MUTED = "#848d9c"
TL_TEXT_FAINT = "#828b99"
TL_PRIMARY = "#00e5cc"
TL_PRIMARY_HOVER = "#33ecd8"
TL_PRIMARY_DIM = "rgba(0,229,204,0.12)"
TL_SUCCESS = "#22c55e"
TL_SUCCESS_DIM = "rgba(34,197,94,0.12)"
# Danger brightened from #ef4444: table .pnl-neg text sits on SURFACE_2 on row
# hover, where the old red measured 4.21 (below AA). #f56565 measures 5.23.
TL_DANGER = "#f56565"
TL_DANGER_DIM = "rgba(245,101,101,0.12)"
TL_WARNING = "#f59e0b"
TL_WARNING_DIM = "rgba(245,158,11,0.12)"
TL_NEUTRAL = "#374151"
TL_NEUTRAL_DIM = "rgba(55,65,81,0.3)"

# Grade scale (A → F): success green through amber to danger red. Grade
# chips are read on PAPER — in the ledger and in trade detail — so the ramp
# follows the light-workspace semantics. The two intermediate steps are the
# matching darker lime and orange, so the ramp still reads as one system.
TL_GRADE_A = TL_SUCCESS_INK
TL_GRADE_B = "#4D7C0F"
TL_GRADE_C = TL_WARNING_INK
TL_GRADE_D = "#B45309"
TL_GRADE_F = TL_DANGER_INK

# =========================================================================
# TYPOGRAPHY TOKENS
# =========================================================================
# SP4: matches the marketing site (site/index.html) so site -> app is one
# brand — Satoshi body, Schibsted Grotesk headings, JetBrains Mono numerals.
# Satoshi is Fontshare-hosted (400/500/700 only — no 600); the rest are
# Google. URLs mirror theme.py exactly so the browser fetches each once.
# Three roles, three faces. Schibsted sets titles only, so it stays an event
# rather than a texture; Satoshi carries everything read as language; mono
# carries everything read as a quantity, where tabular figures stop columns
# from shifting. Fallbacks are system faces — Inter is retired (spec 16
# rejects generic Inter typography) and no new font dependency is added.
TL_FONT_MONO = "'JetBrains Mono', 'SFMono-Regular', Consolas, monospace"
TL_FONT_BODY = "'Satoshi', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
TL_FONT_HEADING = "'Schibsted Grotesk', 'Avenir Next', 'Satoshi', sans-serif"
# Role aliases used by the redesigned surfaces.
TL_FONT_DISPLAY = TL_FONT_HEADING
TL_FONT_UI = TL_FONT_BODY

# =========================================================================
# STRUCTURE TOKENS
# =========================================================================
# Two rule weights, deliberately. The hairline divides things that belong
# together (table rows, KPI cells); the rule marks an aside that comments on
# something else. The Evidence Rail uses the second — at hairline weight the
# signature disappears, at ink weight it competes with the data.
TL_RULE = "#AFBEC0"

# =========================================================================
# MOTION TOKENS (defined here; applied only after the static pass)
# =========================================================================
# Built-in CSS easings are too weak to read as intentional. These are the
# strong variants; durations stay under the 300ms ceiling so no interaction
# ever waits on an animation.
TL_EASE_OUT = "cubic-bezier(0.23, 1, 0.32, 1)"
TL_EASE_IN_OUT = "cubic-bezier(0.77, 0, 0.175, 1)"
TL_EASE_DRAWER = "cubic-bezier(0.32, 0.72, 0, 1)"

_FONT_IMPORT = (
    "https://fonts.googleapis.com/css2?"
    "family=Schibsted+Grotesk:wght@500;600;700&"
    "family=JetBrains+Mono:wght@400;500;600&display=swap"
)
_FONT_IMPORT_FONTSHARE = (
    "https://api.fontshare.com/v2/css?f[]=satoshi@400,500,700&display=swap"
)

# Assets generated via Higgsfield live next to this module.
ASSETS_DIR = Path(__file__).resolve().parent / "assets"

# =========================================================================
# PLOTLY TEMPLATE (single source of truth for chart theming)
# =========================================================================
# Charts are DARK INSTRUMENTS inside the light workspace (spec 7/11.4), so
# the figure paints its own stage rather than inheriting whatever surface
# frames it. This is what makes a chart legible on the light canvas without
# darkening the page around it, and it keeps the bright semantic ramp —
# which needs a dark ground — as the mark colours.
#
# The stage is set here, on the template, because design_system.py is the
# single source of truth for chart theming. Task 6 may centralise a
# `apply_chart_stage` wrapper and the framing radius/padding on top of it;
# the colour contract lives here either way.
PLOTLY_TEMPLATE = go.layout.Template(
    layout=go.Layout(
        paper_bgcolor=TL_CHART_STAGE,
        plot_bgcolor=TL_CHART_STAGE,
        font=dict(family=TL_FONT_BODY, color=TL_TEXT, size=12),
        title=dict(font=dict(size=14, color=TL_TEXT), x=0.0, xanchor="left"),
        # Six marks that stay separable on the stage. The sixth was
        # TL_NEUTRAL, a near-black surface grey that measures 1.71:1 here —
        # it was a background token doing duty as a data colour. TL_TEXT is
        # the light end of the neutral ramp and reads clearly against the
        # mid grey already at position four.
        colorway=[
            TL_PRIMARY,
            TL_WARNING,
            TL_SUCCESS,
            TL_TEXT_MUTED,
            TL_DANGER,
            TL_TEXT,
        ],
        # automargin: once the figure paints its own stage, the stage has a
        # visible edge and pinned page margins clip the tick labels against
        # it. Letting each axis reserve what its labels need fixes every
        # chart at once instead of tuning margins per call site.
        xaxis=dict(
            gridcolor=TL_BORDER,
            zerolinecolor=TL_BORDER,
            automargin=True,
            tickfont=dict(color=TL_TEXT_MUTED, size=11),
            title=dict(font=dict(color=TL_TEXT_MUTED, size=12)),
        ),
        yaxis=dict(
            gridcolor=TL_BORDER,
            zerolinecolor=TL_BORDER,
            automargin=True,
            tickfont=dict(color=TL_TEXT_MUTED, size=11),
            title=dict(font=dict(color=TL_TEXT_MUTED, size=12)),
        ),
        legend=dict(
            bgcolor="rgba(0,0,0,0)",
            font=dict(color=TL_TEXT_MUTED, size=11),
        ),
        hoverlabel=dict(
            bgcolor=TL_SURFACE_2,
            bordercolor=TL_BORDER,
            font=dict(family=TL_FONT_MONO, color=TL_TEXT, size=12),
        ),
    )
)
pio.templates["tradelens"] = PLOTLY_TEMPLATE
pio.templates.default = "tradelens"

_BADGE_VARIANTS = {
    "success",
    "danger",
    "warning",
    "primary",
    "neutral",
    "confidence-high",
    "confidence-medium",
    "confidence-low",
}
_INSIGHT_VARIANTS = {"strength", "leak", "neutral"}
_BANNER_VARIANTS = {"warning", "info", "danger"}


def build_css() -> str:
    """Return the full design-system stylesheet.

    Pure (no Streamlit) so tests can assert on it directly.
    """
    return f"""<style>
/* ============ TRADELENS DESIGN SYSTEM (design_system.py) ============ */
/* Injected after theme.py CSS during migration; later rules win ties. */

/* === FONTS === */
@import url('{_FONT_IMPORT_FONTSHARE}');
@import url('{_FONT_IMPORT}');

/* === CSS VARIABLES === */
:root {{
  /* -- light workspace -- */
  --tl-canvas: {TL_CANVAS}; --tl-paper: {TL_PAPER}; --tl-mist: {TL_MIST};
  --tl-ink: {TL_INK}; --tl-muted: {TL_MUTED};
  --tl-hairline: {TL_HAIRLINE}; --tl-rule: {TL_RULE};
  --tl-action: {TL_ACTION}; --tl-action-hover: {TL_ACTION_HOVER};
  --tl-success-ink: {TL_SUCCESS_INK}; --tl-danger-ink: {TL_DANGER_INK};
  --tl-warning-ink: {TL_WARNING_INK};
  --tl-success-wash: {TL_SUCCESS_WASH}; --tl-danger-wash: {TL_DANGER_WASH};
  --tl-warning-wash: {TL_WARNING_WASH}; --tl-action-wash: {TL_ACTION_WASH};
  /* -- dark instruments -- */
  --tl-rail: {TL_RAIL}; --tl-chart-stage: {TL_CHART_STAGE};
  --tl-focus: {TL_FOCUS};
  --tl-bg: {TL_BG}; --tl-surface: {TL_SURFACE};
  --tl-surface-2: {TL_SURFACE_2};
  --tl-border: {TL_BORDER}; --tl-border-subtle: {TL_BORDER_SUBTLE};
  --tl-text: {TL_TEXT}; --tl-text-muted: {TL_TEXT_MUTED};
  --tl-text-faint: {TL_TEXT_FAINT};
  --tl-primary: {TL_PRIMARY}; --tl-primary-hover: {TL_PRIMARY_HOVER};
  --tl-primary-dim: {TL_PRIMARY_DIM};
  --tl-success: {TL_SUCCESS}; --tl-success-dim: {TL_SUCCESS_DIM};
  --tl-danger: {TL_DANGER}; --tl-danger-dim: {TL_DANGER_DIM};
  --tl-warning: {TL_WARNING}; --tl-warning-dim: {TL_WARNING_DIM};
  --tl-neutral: {TL_NEUTRAL}; --tl-neutral-dim: {TL_NEUTRAL_DIM};
  /* -- type roles -- */
  --tl-font-display: {TL_FONT_DISPLAY};
  --tl-font-ui: {TL_FONT_UI};
  --tl-font-mono: {TL_FONT_MONO};
  --tl-font-body: {TL_FONT_BODY};
  --tl-font-heading: {TL_FONT_HEADING};
  /* -- rhythm: 4/8 base, page tiers 16/24/32/48 -- */
  --tl-space-1: 4px; --tl-space-2: 8px; --tl-space-3: 12px;
  --tl-space-4: 16px; --tl-space-5: 20px; --tl-space-6: 24px;
  --tl-space-8: 32px; --tl-space-12: 48px;
  /* -- 6px controls, 8px panels, 10px overlays -- */
  --tl-radius-sm: 6px; --tl-radius-md: 8px;
  --tl-radius-lg: 10px; --tl-radius-full: 9999px;
  /* -- one elevation; borders and spacing carry hierarchy -- */
  --tl-shadow: 0 1px 2px rgba(19,33,37,0.05), 0 8px 24px rgba(19,33,37,0.07);
  /* -- motion: locked now, applied after the static pass -- */
  --tl-ease-out: {TL_EASE_OUT};
  --tl-ease-in-out: {TL_EASE_IN_OUT};
  --tl-ease-drawer: {TL_EASE_DRAWER};
  --tl-dur-press: 120ms; --tl-dur-state: 160ms;
  --tl-dur-panel: 180ms; --tl-dur-drawer: 240ms;
}}

/* === BASE (proven selectors only) ===
   Background also comes from .streamlit/config.toml [theme]; declared here
   so the workspace does not flash a stale surface before CSS lands. */
[data-testid="stAppViewContainer"] {{
  background: var(--tl-canvas);
  font-family: var(--tl-font-ui);
  color: var(--tl-ink);
}}
/* Schibsted sets titles only — used everywhere it becomes texture. */
[data-testid="stAppViewContainer"] h1,
[data-testid="stAppViewContainer"] h2,
[data-testid="stAppViewContainer"] h3 {{
  font-family: var(--tl-font-display);
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--tl-ink);
}}
[data-testid="stHeader"] {{
  background: transparent;
}}
/* Content width/padding. `.block-container` is anchored to the proven
   stAppViewContainer testid. Cosmetic-only if the class ever changes —
   flagged for visual verification at the phase gate. */
[data-testid="stAppViewContainer"] .block-container {{
  padding-top: 1.5rem;
  padding-bottom: 2rem;
  max-width: 1320px;
}}

/* === SIDEBAR — the dark architectural rail ===
   Ink-dark against the light canvas so the workspace reads as a plane the
   navigation sits beside, not a panel floating on top of it. */
[data-testid="stSidebar"] {{
  background: var(--tl-rail);
  border-right: 1px solid var(--tl-border);
  color: var(--tl-text);
}}
[data-testid="stSidebar"] a,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {{
  color: var(--tl-text);
}}
/* Nav links (st.page_link renders an anchor): quiet rest state, surface
   hover, visible keyboard focus. */
[data-testid="stSidebar"] a {{
  border-radius: var(--tl-radius-sm);
  transition: background var(--tl-dur-state) var(--tl-ease-out);
}}
@media (hover: hover) and (pointer: fine) {{
  [data-testid="stSidebar"] a:hover {{
    background: var(--tl-surface-2);
  }}
}}
[data-testid="stSidebar"] a:focus-visible {{
  outline: 2px solid var(--tl-primary);
  outline-offset: 2px;
}}
/* === APP SHELL — navigation architecture (components/sidebar.py) ===
   Selectors are the data-testid values verified in the browser against the
   pinned streamlit==1.50.0 DOM. Streamlit marks the current page only with
   a generated class whose hash changes between releases, so the active
   state rides on our own keyed containers instead. */

/* --- destination rows --- */
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] {{
  min-height: 44px;
  display: flex;
  align-items: center;
  gap: var(--tl-space-2);
  padding: 0 var(--tl-space-3);
  border-radius: var(--tl-radius-sm);
  color: var(--tl-text);
  position: relative;
  transition: background var(--tl-dur-state) var(--tl-ease-out);
}}
@media (hover: hover) and (pointer: fine) {{
  [data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover {{
    background: var(--tl-surface-2);
  }}
}}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:focus-visible {{
  outline: 2px solid var(--tl-focus);
  outline-offset: -2px;
}}
/* Press feedback only — these rows are visited dozens of times a session,
   so nothing here is allowed to take time to finish. */
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:active {{
  background: var(--tl-surface-2);
}}

/* --- the current destination ---
   Three cues, none of them colour on its own: a teal indicator bar, a
   heavier label, and a raised surface. */
[class*="st-key-tl_nav_"][class*="_active"] [data-testid="stPageLink-NavLink"] {{
  background: var(--tl-surface-2);
  font-weight: 700;
}}
[class*="st-key-tl_nav_"][class*="_active"]
  [data-testid="stPageLink-NavLink"]::before {{
  content: '';
  position: absolute;
  left: 0;
  top: 10px;
  bottom: 10px;
  width: 3px;
  border-radius: 0 2px 2px 0;
  background: var(--tl-focus);
}}

/* --- the persistent action ---
   One filled control in the rail. Bright teal is the action colour on a
   dark surface; the rail ink reads 11.3:1 on it. */
.st-key-tl_nav_action {{
  margin: var(--tl-space-2) 0 var(--tl-space-4) 0;
}}
.st-key-tl_nav_action [data-testid="stPageLink-NavLink"] {{
  background: var(--tl-focus);
  color: var(--tl-rail);
  font-weight: 600;
  justify-content: center;
  transition: opacity var(--tl-dur-state) var(--tl-ease-out),
              transform var(--tl-dur-press) var(--tl-ease-out);
}}
@media (hover: hover) and (pointer: fine) {{
  .st-key-tl_nav_action [data-testid="stPageLink-NavLink"]:hover {{
    background: var(--tl-focus);
    opacity: 0.92;
  }}
}}
.st-key-tl_nav_action [data-testid="stPageLink-NavLink"]:active {{
  background: var(--tl-focus);
  transform: scale(0.98);
}}
.st-key-tl_nav_action [data-testid="stPageLink-NavLink"]::before {{
  content: none;
}}

/* --- utility group --- */
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{
  color: var(--tl-text-muted);
}}

/* --- tablet: a narrower rail, same hierarchy --- */
@media (min-width: 641px) and (max-width: 1023px) {{
  [data-testid="stSidebar"] {{ width: 208px; min-width: 208px; }}
  [data-testid="stAppViewContainer"] .block-container {{
    padding-left: var(--tl-space-4);
    padding-right: var(--tl-space-4);
  }}
}}

/* --- mobile bottom navigation ---
   Its own five-item hierarchy, not the rail shrunk down. Hidden entirely
   above the phone breakpoint so it is never a second nav competing with
   the rail. */
.tl-mobile-nav {{
  display: none;
}}
/* Anchored to the app container: Streamlit's own markdown-anchor rule
   outranks a bare class, so an unanchored selector leaves the bar rendering
   in the browser's default link blue with underlines. */
[data-testid="stAppViewContainer"] a.tl-mobile-nav-item,
.tl-mobile-nav-item {{
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  flex: 1 1 0;
  min-height: 44px;
  padding: 6px 4px;
  text-decoration: none;
  color: var(--tl-text-muted);
  transition: color var(--tl-dur-state) var(--tl-ease-out),
              transform var(--tl-dur-press) var(--tl-ease-out);
}}
.tl-mobile-nav-item:active {{
  transform: scale(0.96);
}}
.tl-mobile-nav-item:focus-visible {{
  outline: 2px solid var(--tl-focus);
  outline-offset: -2px;
  border-radius: var(--tl-radius-sm);
}}
.tl-mobile-nav-icon {{
  font-family: 'Material Symbols Rounded';
  font-size: 22px;
  line-height: 1;
  font-weight: 300;
}}
.tl-mobile-nav-label {{
  font-size: 11px;
  line-height: 14px;
  font-weight: 500;
}}
/* Current item: teal, heavier, and topped by an indicator bar. */
[data-testid="stAppViewContainer"] a.tl-mobile-nav-item.is-active,
.tl-mobile-nav-item.is-active {{
  color: var(--tl-focus);
}}
.tl-mobile-nav-item.is-active .tl-mobile-nav-label {{
  font-weight: 700;
}}
.tl-mobile-nav-item.is-active::before {{
  content: '';
  position: absolute;
  top: 0;
  width: 24px;
  height: 2px;
  border-radius: 0 0 2px 2px;
  background: var(--tl-focus);
}}

/* Sidebar brand block + status note (replaces inline styles in sidebar.py) */
.tl-side-brand {{
  display: flex;
  align-items: center;
  gap: var(--tl-space-2);
}}
.tl-side-brand-name {{
  font-weight: 700;
  font-size: 1.05rem;
  letter-spacing: -0.01em;
  color: var(--tl-text);
}}
.tl-side-brand-sub {{
  color: var(--tl-text-muted);
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  margin: 2px 0 var(--tl-space-3) 28px;
}}
.tl-side-note {{
  border: 1px solid var(--tl-border);
  background: var(--tl-surface-2);
  border-radius: var(--tl-radius-sm);
  padding: var(--tl-space-2) var(--tl-space-3);
  margin: var(--tl-space-3) 0;
  font-size: 12px;
  line-height: 1.45;
  color: var(--tl-text-muted);
}}
.tl-side-note b {{
  color: var(--tl-text);
  font-weight: 700;
}}
/* Active state, so the teal edge is functional rather than decoration.
   The colour was a literal rgba(0,194,178,.3) — the pre-SP4 teal, left
   behind when the brand collapsed onto one accent. */
.tl-side-note.active {{
  border-color: var(--tl-focus);
  background: var(--tl-primary-dim);
  color: var(--tl-primary);
}}
.tl-side-note.active b {{
  color: var(--tl-primary);
}}

/* === NATIVE METRICS (proven stMetric* set; replaces the legacy
       'metric-container' selector from the spec) === */
.stMetric {{
  background: var(--tl-paper);
  border: 1px solid var(--tl-hairline);
  border-radius: var(--tl-radius-md);
  padding: 12px 16px;
}}
.stMetric [data-testid="stMetricValue"] {{
  font-family: var(--tl-font-mono);
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  color: var(--tl-ink);
}}
.stMetric [data-testid="stMetricDelta"] {{
  font-family: var(--tl-font-mono);
}}
.stMetric [data-testid="stMetricLabel"] {{
  color: var(--tl-muted);
}}

/* === BUTTONS (all states: rest, hover, focus, active) ===
   Form submit buttons (Sign In, Save Trade, …) are primary actions too —
   they get the identical treatment as .stButton. */
.stButton > button,
.stFormSubmitButton > button {{
  background: var(--tl-action);
  color: var(--tl-paper);
  border: 1px solid var(--tl-action);
  border-radius: var(--tl-radius-sm);
  font-family: var(--tl-font-ui);
  font-weight: 500;
  transition: background var(--tl-dur-state) var(--tl-ease-out),
              border-color var(--tl-dur-state) var(--tl-ease-out);
}}
@media (hover: hover) and (pointer: fine) {{
  .stButton > button:hover,
  .stFormSubmitButton > button:hover {{
    background: var(--tl-action-hover);
    border-color: var(--tl-action-hover);
  }}
}}
.stButton > button:focus-visible,
.stFormSubmitButton > button:focus-visible {{
  outline: 2px solid var(--tl-action);
  outline-offset: 2px;
}}
.stButton > button:active,
.stFormSubmitButton > button:active {{
  background: var(--tl-action-hover);
}}
/* The rail holds exactly ONE filled action — "Log completed trade". Sign
   out is a utility control, so it is outlined: two filled teal buttons in
   one column read as two primaries and the eye cannot tell which matters. */
[data-testid="stSidebar"] .stButton > button {{
  background: transparent;
  border-color: var(--tl-border);
  color: var(--tl-text);
  min-height: 44px;
}}
@media (hover: hover) and (pointer: fine) {{
  [data-testid="stSidebar"] .stButton > button:hover {{
    background: var(--tl-surface-2);
    border-color: var(--tl-text-muted);
  }}
}}
[data-testid="stSidebar"] .stButton > button:focus-visible {{
  outline: 2px solid var(--tl-focus);
}}

/* === SECONDARY ACTIONS ===
   Solid teal is reserved for the one action that moves the trader forward
   (save, start, continue). Resets, regenerates and retries are outlined so
   a page has a single obvious primary. Scoped by widget key — give the
   control a key beginning "secondary_" — because bare button selectors
   would repaint every button on the page. */
[class*="st-key-secondary_"] button {{
  background: transparent;
  color: var(--tl-ink);
  border-color: var(--tl-hairline);
}}
@media (hover: hover) and (pointer: fine) {{
  [class*="st-key-secondary_"] button:hover {{
    background: var(--tl-mist);
    border-color: var(--tl-muted);
  }}
}}
[class*="st-key-secondary_"] button:active {{
  background: var(--tl-mist);
}}

/* =====================================================================
   PREMIUM WORKSPACE PRIMITIVES (components/workspace.py)
   ===================================================================== */

/* --- text carried to screen readers only ---
   Used where meaning is otherwise expressed by colour alone. Clipped
   rather than display:none, which would remove it from the a11y tree. */
.tl-visually-hidden {{
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  padding: 0;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
  border: 0;
}}

/* --- page masthead --- */
.tl-masthead {{
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--tl-space-4);
  flex-wrap: wrap;
  padding-bottom: var(--tl-space-4);
  border-bottom: 1px solid var(--tl-hairline);
  margin-bottom: var(--tl-space-6);
}}
.tl-masthead-lede {{ min-width: 0; }}
.tl-masthead-eyebrow {{
  font-family: var(--tl-font-mono);
  font-size: 12px;
  line-height: 18px;
  font-weight: 500;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--tl-muted);
  margin: 0 0 var(--tl-space-1) 0;
}}
.tl-masthead-title {{
  font-family: var(--tl-font-display);
  font-size: 30px;
  line-height: 36px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--tl-ink);
  margin: 0;
}}
.tl-masthead-subtitle {{
  font-size: 14px;
  line-height: 20px;
  color: var(--tl-muted);
  margin: var(--tl-space-1) 0 0 0;
  max-width: 68ch;
}}
.tl-masthead-meta {{
  font-family: var(--tl-font-mono);
  font-size: 12px;
  line-height: 18px;
  color: var(--tl-muted);
  margin: 0;
  white-space: nowrap;
}}

/* --- ruled KPI strip ---
   One measurement across a period, divided by hairlines. Six boxed tiles
   would say these numbers are six separate things; they are not. */
.tl-kpi-strip {{
  display: flex;
  flex-wrap: wrap;
  background: var(--tl-paper);
  border: 1px solid var(--tl-hairline);
  border-radius: var(--tl-radius-md);
  margin-bottom: var(--tl-space-6);
}}
.tl-kpi-cell {{
  flex: 1 1 150px;
  min-width: 0;
  padding: var(--tl-space-3) var(--tl-space-4);
}}
.tl-kpi-cell + .tl-kpi-cell {{
  border-left: 1px solid var(--tl-hairline);
}}
.tl-kpi-key {{
  font-size: 12px;
  line-height: 18px;
  font-weight: 500;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--tl-muted);
  margin: 0;
}}
.tl-kpi-figure {{
  font-family: var(--tl-font-mono);
  font-variant-numeric: tabular-nums;
  font-size: 28px;
  line-height: 34px;
  font-weight: 500;
  letter-spacing: -0.02em;
  color: var(--tl-ink);
  margin: var(--tl-space-1) 0 0 0;
}}
.tl-kpi-cell.tone-positive .tl-kpi-figure {{ color: var(--tl-success-ink); }}
.tl-kpi-cell.tone-negative .tl-kpi-figure {{ color: var(--tl-danger-ink); }}
.tl-kpi-cell.tone-warning .tl-kpi-figure {{ color: var(--tl-warning-ink); }}
.tl-kpi-detail {{
  font-family: var(--tl-font-mono);
  font-size: 12px;
  line-height: 18px;
  color: var(--tl-muted);
  margin: var(--tl-space-1) 0 0 0;
}}

/* --- EVIDENCE RAIL: the signature ---
   A margin annotation, not a card: neutral rule, indented content, mono
   metadata. No fill and no radius, so it reads as commentary beside the
   data rather than another object competing with it. */
.tl-evidence-rail {{
  border-left: 2px solid var(--tl-rule);
  padding-left: var(--tl-space-3);
  margin: var(--tl-space-4) 0 0 0;
  max-width: 68ch;
}}
.tl-evidence-label {{
  font-family: var(--tl-font-mono);
  font-size: 12px;
  line-height: 18px;
  font-weight: 500;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--tl-muted);
  margin: 0;
}}
.tl-evidence-claim {{
  font-size: 14px;
  line-height: 20px;
  color: var(--tl-ink);
  margin: var(--tl-space-1) 0 0 0;
}}
.tl-evidence-facts {{
  display: flex;
  flex-wrap: wrap;
  gap: var(--tl-space-1) var(--tl-space-4);
  margin: var(--tl-space-2) 0 0 0;
}}
.tl-evidence-fact {{
  display: flex;
  align-items: baseline;
  gap: var(--tl-space-2);
  min-width: 0;
}}
.tl-evidence-facts dt {{
  font-size: 12px;
  line-height: 18px;
  font-weight: 500;
  color: var(--tl-muted);
  margin: 0;
}}
.tl-evidence-facts dd {{
  font-family: var(--tl-font-mono);
  font-size: 12px;
  line-height: 18px;
  color: var(--tl-ink);
  margin: 0;
}}
/* Confidence is spelled out and marked — never color alone. */
.tl-evidence-confidence::before {{
  content: '';
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-right: 6px;
  border-radius: var(--tl-radius-full);
  background: var(--tl-muted);
}}
.tl-evidence-confidence.conf-high::before {{ background: var(--tl-success-ink); }}
.tl-evidence-confidence.conf-medium::before {{ background: var(--tl-warning-ink); }}

/* --- numbered research finding --- */
.tl-finding {{
  display: flex;
  gap: var(--tl-space-4);
  padding: var(--tl-space-6) 0;
  border-top: 1px solid var(--tl-hairline);
}}
.tl-finding-number {{
  font-family: var(--tl-font-mono);
  font-size: 14px;
  line-height: 24px;
  font-weight: 500;
  color: var(--tl-muted);
  margin: 0;
  flex: 0 0 2.5rem;
}}
.tl-finding-body {{ min-width: 0; }}
.tl-finding-title {{
  font-family: var(--tl-font-ui);
  font-size: 17px;
  line-height: 24px;
  font-weight: 700;
  color: var(--tl-ink);
  margin: 0;
}}
.tl-finding-text {{
  font-size: 16px;
  line-height: 25px;
  color: var(--tl-ink);
  margin: var(--tl-space-2) 0 0 0;
  max-width: 68ch;
}}

/* --- editorial readout (interpretation beneath a chart) --- */
.tl-readout {{
  padding-top: var(--tl-space-4);
  border-top: 1px solid var(--tl-hairline);
  margin-top: var(--tl-space-4);
}}
.tl-readout-title {{
  font-family: var(--tl-font-ui);
  font-size: 17px;
  line-height: 24px;
  font-weight: 700;
  color: var(--tl-ink);
  margin: 0;
}}
.tl-readout-body {{
  font-size: 16px;
  line-height: 25px;
  color: var(--tl-ink);
  margin: var(--tl-space-2) 0 0 0;
  max-width: 68ch;
}}

/* --- active filter summary --- */
.tl-filter-summary {{
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--tl-space-2);
  margin-bottom: var(--tl-space-3);
}}
.tl-filter-chip {{
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  padding: 2px 10px;
  border: 1px solid var(--tl-hairline);
  border-radius: var(--tl-radius-full);
  background: var(--tl-mist);
  font-size: 12px;
  line-height: 18px;
}}
.tl-filter-key {{
  color: var(--tl-muted);
  font-weight: 500;
}}
.tl-filter-value {{
  font-family: var(--tl-font-mono);
  color: var(--tl-ink);
}}
.tl-filter-empty {{
  font-size: 12px;
  line-height: 18px;
  color: var(--tl-muted);
}}

/* --- surfaces: white sheet, dark instrument stage, dark reading sheet --- */
.tl-sheet {{
  background: var(--tl-paper);
  border: 1px solid var(--tl-hairline);
  border-radius: var(--tl-radius-md);
  padding: var(--tl-space-6);
}}
.tl-chart-stage {{
  background: var(--tl-chart-stage);
  border-radius: var(--tl-radius-md);
  padding: var(--tl-space-4);
  color: var(--tl-text);
}}
.tl-ink-sheet {{
  background: var(--tl-chart-stage);
  border-radius: var(--tl-radius-md);
  padding: var(--tl-space-6);
  color: var(--tl-text);
}}
.tl-ink-sheet .tl-finding-title,
.tl-ink-sheet .tl-finding-text,
.tl-ink-sheet .tl-evidence-claim,
.tl-ink-sheet .tl-readout-title,
.tl-ink-sheet .tl-readout-body {{ color: var(--tl-text); }}
.tl-ink-sheet .tl-evidence-label,
.tl-ink-sheet .tl-finding-number,
.tl-ink-sheet .tl-evidence-facts dt {{ color: var(--tl-text-muted); }}
.tl-ink-sheet .tl-evidence-facts dd {{ color: var(--tl-text); }}
.tl-ink-sheet .tl-evidence-rail {{ border-left-color: var(--tl-border); }}
.tl-ink-sheet .tl-finding,
.tl-ink-sheet .tl-readout {{ border-top-color: var(--tl-border); }}
.tl-ink-sheet .tl-evidence-confidence.conf-high::before {{
  background: var(--tl-success);
}}
.tl-ink-sheet .tl-evidence-confidence.conf-medium::before {{
  background: var(--tl-warning);
}}

/* === KPI CARD (legacy single-card form; superseded by .tl-kpi-strip) === */
.tl-kpi-card {{
  background: var(--tl-paper);
  border: 1px solid var(--tl-hairline);
  border-radius: var(--tl-radius-md);
  padding: var(--tl-space-4);
}}
.tl-kpi-label {{
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--tl-muted);
}}
.tl-kpi-value {{
  font-size: 26px;
  font-weight: 500;
  font-family: var(--tl-font-mono);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
  white-space: nowrap;
  color: var(--tl-ink);
  line-height: 1.1;
  margin-top: 4px;
}}
.tl-kpi-value.positive {{ color: var(--tl-success-ink); }}
.tl-kpi-value.negative {{ color: var(--tl-danger-ink); }}
.tl-kpi-value.missing {{ color: var(--tl-muted); }}
.tl-kpi-delta {{
  font-size: 12px;
  font-family: var(--tl-font-mono);
  margin-top: 2px;
  color: var(--tl-muted);
}}
.tl-kpi-delta.positive {{ color: var(--tl-success-ink); }}
.tl-kpi-delta.negative {{ color: var(--tl-danger-ink); }}

/* === INSIGHT CARD ===
   Variants use tinted backgrounds + accent icon (NO colored side
   borders — PRODUCT.md anti-pattern; owner decision 2026-07-06). */
.tl-insight-card {{
  background: var(--tl-paper);
  border: 1px solid var(--tl-hairline);
  border-radius: var(--tl-radius-md);
  padding: var(--tl-space-4);
}}
.tl-insight-card.strength {{ background: var(--tl-success-wash); }}
.tl-insight-card.leak {{ background: var(--tl-danger-wash); }}
.tl-insight-card.neutral {{ background: var(--tl-mist); }}
.tl-insight-head {{
  display: flex;
  align-items: center;
  gap: var(--tl-space-2);
  margin-bottom: var(--tl-space-2);
}}
.tl-insight-icon {{ font-size: 16px; }}
.tl-insight-card.strength .tl-insight-icon {{ color: var(--tl-success-ink); }}
.tl-insight-card.leak .tl-insight-icon {{ color: var(--tl-danger-ink); }}
.tl-insight-card.neutral .tl-insight-icon {{ color: var(--tl-muted); }}
.tl-insight-title {{
  font-size: 14px;
  font-weight: 500;
  color: var(--tl-ink);
  flex: 1;
}}
.tl-insight-body {{
  font-size: 14px;
  line-height: 20px;
  color: var(--tl-ink);
  margin: 0 0 var(--tl-space-2) 0;
}}
.tl-insight-evidence {{
  font-size: 12px;
  color: var(--tl-muted);
  margin: 0;
}}

/* === AI CARD ===
   Neutral border, not a teal outline: a passive container that happens to
   hold generated text is not an action (spec 8). */
.tl-ai-card {{
  background: var(--tl-paper);
  border: 1px solid var(--tl-hairline);
  border-radius: var(--tl-radius-md);
  padding: var(--tl-space-4);
  position: relative;
}}
.tl-ai-card::before {{
  content: 'AI';
  position: absolute;
  top: var(--tl-space-2);
  right: var(--tl-space-3);
  font-family: var(--tl-font-mono);
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.12em;
  color: var(--tl-muted);
}}

/* === FORM SECTION CARD === */
.tl-form-card {{
  background: var(--tl-paper);
  border: 1px solid var(--tl-hairline);
  border-radius: var(--tl-radius-md);
  padding: var(--tl-space-6);
  margin-bottom: var(--tl-space-4);
}}
.tl-form-card h3 {{
  font-size: 14px;
  font-weight: 500;
  color: var(--tl-ink);
  margin-bottom: var(--tl-space-4);
}}

/* === EMPTY STATE CARD === */
.tl-empty-card {{
  background: var(--tl-paper);
  border: 1px dashed var(--tl-hairline);
  border-radius: var(--tl-radius-md);
  padding: var(--tl-space-8);
  text-align: center;
}}
.tl-empty-card .icon {{
  font-size: 32px;
  margin-bottom: var(--tl-space-3);
  opacity: 0.4;
}}
.tl-empty-card h4 {{
  font-size: 14px;
  font-weight: 500;
  color: var(--tl-ink);
  margin-bottom: var(--tl-space-2);
}}
.tl-empty-card p {{
  font-size: 14px;
  line-height: 20px;
  color: var(--tl-muted);
  max-width: 46ch;
  margin: 0 auto;
}}
/* Onboarding next step. Quiet by design: it sits above the dashboard a
   new trader is trying to read, so it uses the standard surface with a
   neutral hairline. The mono step count carries the only accent — a
   colored side border is a documented anti-pattern here. */
.tl-next-step {{
  border: 1px solid var(--tl-hairline);
  border-radius: var(--tl-radius-md);
  background: var(--tl-paper);
  padding: var(--tl-space-4) var(--tl-space-5);
  margin-bottom: var(--tl-space-4);
}}
.tl-next-step-count {{
  font-family: var(--tl-font-mono);
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--tl-action);
}}
.tl-next-step-label {{
  font-size: 17px;
  line-height: 24px;
  font-weight: 700;
  color: var(--tl-ink);
  margin-top: var(--tl-space-1);
}}
.tl-next-step-detail {{
  font-size: 14px;
  line-height: 20px;
  color: var(--tl-muted);
  margin-top: var(--tl-space-1);
}}

/* Low-data explanation shown in place of a chart. Same surface as the
   empty card, but compact: an explanation should not occupy the canvas
   the withheld chart would have. Spacing only — no new colors. */
.tl-data-state .tl-empty-card {{
  padding: var(--tl-space-6) var(--tl-space-5);
  text-align: left;
}}
.tl-data-state .tl-empty-card .icon {{
  font-size: 18px;
  margin-bottom: var(--tl-space-2);
}}
.tl-data-state .tl-empty-card p {{
  max-width: 46ch;
  margin: 0;
}}
.tl-empty-img {{
  max-width: 280px;
  width: 100%;
  border-radius: var(--tl-radius-md);
  margin-bottom: var(--tl-space-4);
}}
.tl-empty-action {{
  margin-top: var(--tl-space-3);
  font-size: 14px;
  font-weight: 500;
  color: var(--tl-action);
}}

/* === BADGES / CHIPS ===
   Ink label on a quiet ground, with the hue carried by a dot. Colored text
   on a tint of its own hue is both the generic-SaaS badge look and a
   contrast trap (see the wash tokens); a dot also means the state survives
   for a reader who cannot separate the hues at all. */
.tl-badge {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 10px;
  border-radius: var(--tl-radius-full);
  font-size: 12px;
  line-height: 18px;
  font-weight: 500;
  color: var(--tl-ink);
}}
.tl-badge-success::before,
.tl-badge-danger::before,
.tl-badge-warning::before,
.tl-badge-primary::before,
.tl-confidence-high::before,
.tl-confidence-medium::before {{
  content: '';
  flex: 0 0 auto;
  width: 6px;
  height: 6px;
  border-radius: var(--tl-radius-full);
  background: var(--tl-muted);
}}
.tl-badge-success {{ background: var(--tl-success-wash); }}
.tl-badge-success::before {{ background: var(--tl-success-ink); }}
.tl-badge-danger {{ background: var(--tl-danger-wash); }}
.tl-badge-danger::before {{ background: var(--tl-danger-ink); }}
.tl-badge-warning {{ background: var(--tl-warning-wash); }}
.tl-badge-warning::before {{ background: var(--tl-warning-ink); }}
.tl-badge-primary {{ background: var(--tl-action-wash); }}
.tl-badge-primary::before {{ background: var(--tl-action); }}
/* Neutral chips carry setup and tag names — a grey dot on every tag is
   noise, so the neutral variant stays unmarked. */
.tl-badge-neutral {{
  background: var(--tl-mist);
  color: var(--tl-muted);
}}
.tl-confidence-high {{ background: var(--tl-success-wash); }}
.tl-confidence-high::before {{ background: var(--tl-success-ink); }}
.tl-confidence-medium {{ background: var(--tl-warning-wash); }}
.tl-confidence-medium::before {{ background: var(--tl-warning-ink); }}
.tl-confidence-low {{
  background: var(--tl-mist);
  color: var(--tl-muted);
}}
.tl-chip-row {{
  display: flex;
  flex-wrap: wrap;
  gap: var(--tl-space-2);
  align-items: center;
}}

/* === SECTION HEADER ===
   Signature mark: the short teal top-rule (same motif as the landing
   feature cards) replaces generic dividers as the section break. */
.tl-section-header {{
  margin: var(--tl-space-8) 0 var(--tl-space-4) 0;
}}
.tl-section-header::before {{
  content: '';
  display: block;
  width: 20px;
  height: 2px;
  background: var(--tl-action);
  margin-bottom: var(--tl-space-2);
}}
.tl-section-title {{
  font-family: var(--tl-font-display);
  font-size: 22px;
  line-height: 28px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--tl-ink);
}}
.tl-section-subtitle {{
  font-size: 14px;
  line-height: 20px;
  color: var(--tl-muted);
  margin-top: 2px;
}}
/* Chart card title (analytics) — one quiet weight below section titles. */
.tl-chart-title {{
  font-size: 14px;
  font-weight: 500;
  letter-spacing: 0.01em;
  color: var(--tl-ink);
  margin: 0 0 var(--tl-space-2) 0;
}}
.tl-chart-stage .tl-chart-title {{ color: var(--tl-text); }}

/* === ERROR BOX (components/ui.error_box) ===
   Red is reserved for errors, so this is one of the few places the danger
   hue is load-bearing. Same rule as the banners: ink copy on the danger
   wash with the hue as a border and mark, never as the text colour. */
.tl-error-box {{
  border: 1px solid var(--tl-danger-ink);
  border-radius: var(--tl-radius-sm);
  background: var(--tl-danger-wash);
  padding: var(--tl-space-3) var(--tl-space-4);
  color: var(--tl-ink);
  font-size: 14px;
  line-height: 20px;
  white-space: pre-wrap;
}}
.tl-error-box::before {{
  content: '';
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-right: var(--tl-space-2);
  vertical-align: 1px;
  border-radius: var(--tl-radius-full);
  background: var(--tl-danger-ink);
}}

/* === BANNERS ===
   Same rule as badges: ink copy on a quiet ground, hue carried by a mark. */
.tl-banner {{
  border-radius: var(--tl-radius-sm);
  border: 1px solid var(--tl-hairline);
  padding: var(--tl-space-3) var(--tl-space-4);
  font-size: 14px;
  line-height: 20px;
  color: var(--tl-ink);
  margin-bottom: var(--tl-space-4);
}}
.tl-banner::before {{
  content: '';
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-right: var(--tl-space-2);
  vertical-align: 1px;
  border-radius: var(--tl-radius-full);
  background: var(--tl-muted);
}}
.tl-banner-warning {{ background: var(--tl-warning-wash); }}
.tl-banner-warning::before {{ background: var(--tl-warning-ink); }}
.tl-banner-info {{ background: var(--tl-action-wash); }}
.tl-banner-info::before {{ background: var(--tl-action); }}
.tl-banner-danger {{ background: var(--tl-danger-wash); }}
.tl-banner-danger::before {{ background: var(--tl-danger-ink); }}

/* === STEP INDICATOR === */
.tl-stepper {{
  display: flex;
  align-items: center;
  margin-bottom: var(--tl-space-8);
}}
.tl-step {{
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
}}
.tl-step-circle {{
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
}}
.tl-step-circle.done {{ background: var(--tl-action); color: var(--tl-paper); }}
.tl-step-circle.active {{
  background: var(--tl-action);
  color: var(--tl-paper);
  box-shadow: 0 0 0 3px var(--tl-action-wash);
}}
.tl-step-circle.future {{
  background: var(--tl-mist);
  color: var(--tl-muted);
}}
.tl-step-label {{
  font-size: 12px;
  line-height: 18px;
  color: var(--tl-muted);
  margin-top: 4px;
}}
.tl-step-connector {{
  flex: 1;
  height: 2px;
  margin-bottom: 16px;
}}
.tl-step-connector.done {{ background: var(--tl-action); }}
.tl-step-connector.future {{ background: var(--tl-hairline); }}

/* === TRADE WIZARD (components/trade_wizard.py + pages/1_NewTrade.py) === */

/* Step transition. The step container's key changes with the step, so
   Streamlit mounts a new element and this replays — transform and opacity
   only, inside the 180-240ms window, and never on focus or validation
   text, which must appear the instant they exist. */
[class*="st-key-tl_step_"] {{
  animation: tl-step-in 200ms var(--tl-ease-out) both;
}}
@keyframes tl-step-in {{
  from {{ opacity: 0; transform: translateY(4px); }}
  to {{ opacity: 1; transform: none; }}
}}

/* Progress. One system: the numbered rail on desktop, and the masthead
   eyebrow's "Step N of 5" everywhere. Below the phone breakpoint the rail
   would wrap into two lines of circles, so it is withdrawn rather than
   shrunk. */
.tl-wizard-progress {{
  margin-bottom: var(--tl-space-6);
}}
.tl-wizard-progress .tl-stepper {{
  margin-bottom: 0;
}}

/* Sticky action bar. Sticky, not fixed: it stays in the document flow, so
   it can never sit on top of the last field of a step. */
.st-key-tl_wizard_bar {{
  position: sticky;
  bottom: 0;
  z-index: 20;
  background: var(--tl-canvas);
  border-top: 1px solid var(--tl-hairline);
  padding: var(--tl-space-3) 0 var(--tl-space-2) 0;
  margin-top: var(--tl-space-6);
}}
.tl-wizard-draft {{
  font-family: var(--tl-font-mono);
  font-size: 12px;
  line-height: 18px;
  color: var(--tl-muted);
  text-align: center;
  margin: 0;
  padding-top: var(--tl-space-3);
}}
/* The bar's controls are the ones a trader hits five times per trade, so
   they carry the 44px minimum at every width — not only on touch. */
.st-key-tl_wizard_bar .stButton > button {{
  min-height: 44px;
}}

/* === QUICK ACTION CARD (rest, hover, focus-within states) === */
.tl-action-card {{
  display: block;
  background: var(--tl-paper);
  border: 1px solid var(--tl-hairline);
  border-radius: var(--tl-radius-md);
  padding: var(--tl-space-4);
  cursor: pointer;
  transition: border-color var(--tl-dur-state) var(--tl-ease-out);
}}
@media (hover: hover) and (pointer: fine) {{
  .tl-action-card:hover {{
    border-color: var(--tl-action);
  }}
}}
.tl-action-card:focus-within {{
  border-color: var(--tl-action);
  box-shadow: var(--tl-shadow);
}}

/* === HERO KPI ROW (dashboard) ===
   Superseded by .tl-kpi-strip; kept legible until Overview is recomposed.
   The background image the dark hero carried is not reinstated on the
   light workspace — decoration behind figures is what made the old
   dashboard hard to read. */
.tl-hero-wrap {{
  border: 1px solid var(--tl-hairline);
  border-radius: var(--tl-radius-md);
  padding: var(--tl-space-6);
  margin-bottom: var(--tl-space-4);
  background-color: var(--tl-paper);
}}
.tl-kpi-row {{
  display: flex;
  gap: var(--tl-space-3);
  flex-wrap: wrap;
}}
.tl-kpi-row .tl-kpi-card {{
  flex: 1 1 150px;
  min-width: 150px;
  background: var(--tl-paper);
}}

/* === DATA LEDGER (recent trades etc.) ===
   Ledger density: 14px text, generous row padding, hairline row rules, and
   tabular figures so money columns line up on the decimal. Rows change
   background on hover only — a ledger is scanned dozens of times a session,
   and rows that lift or scale make that feel slow. */
.tl-table-wrap {{ overflow-x: auto; }}
.tl-table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
  line-height: 20px;
}}
.tl-table th {{
  text-align: left;
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--tl-muted);
  padding: var(--tl-space-2) var(--tl-space-3);
  border-bottom: 1px solid var(--tl-hairline);
}}
.tl-table td {{
  padding: var(--tl-space-3);
  border-bottom: 1px solid var(--tl-hairline);
  color: var(--tl-ink);
  transition: background var(--tl-dur-state) var(--tl-ease-out);
}}
.tl-table td.mono {{
  font-family: var(--tl-font-mono);
  font-variant-numeric: tabular-nums;
}}
.tl-table th.num, .tl-table td.num {{ text-align: right; }}
.tl-table td.pnl-pos {{ color: var(--tl-success-ink); }}
.tl-table td.pnl-neg {{ color: var(--tl-danger-ink); }}
/* Gated: on a touch device :hover latches after a tap, leaving a row
   tinted as though it were selected. */
@media (hover: hover) and (pointer: fine) {{
  .tl-table tr:hover td {{ background: var(--tl-mist); }}
}}

/* === WELCOME (dashboard first-run empty state) === */
.tl-welcome {{
  text-align: center;
  padding: var(--tl-space-8) 0;
}}
.tl-welcome-img {{
  width: 100%;
  border-radius: var(--tl-radius-md);
  margin-bottom: var(--tl-space-6);
}}
.tl-welcome-title {{
  font-family: var(--tl-font-display);
  font-size: 30px;
  line-height: 36px;
  font-weight: 700;
  color: var(--tl-ink);
  margin: 0 0 var(--tl-space-2) 0;
}}
.tl-welcome-sub {{
  font-size: 16px;
  line-height: 25px;
  color: var(--tl-muted);
  margin: 0 0 var(--tl-space-4) 0;
}}
.tl-welcome-cta-img {{
  width: 300px;
  max-width: 100%;
  border-radius: var(--tl-radius-md);
  margin: var(--tl-space-4) auto;
  display: block;
}}

/* === QUICK ACTION CARD CONTENT ===
   Inner elements are SPANS forced to display:block — block tags inside an
   inline <a> get re-parsed by the markdown renderer and break the card.
   The testid-anchored selector outranks Streamlit's own markdown-anchor
   color/underline rules. */
[data-testid="stAppViewContainer"] a.tl-action-link {{
  text-decoration: none;
  color: inherit;
  display: block;
}}
.tl-action-title {{
  display: block;
  font-size: 14px;
  font-weight: 500;
  color: var(--tl-ink);
  margin-bottom: 2px;
}}
.tl-action-sub {{
  display: block;
  font-size: 12px;
  color: var(--tl-muted);
  margin-bottom: var(--tl-space-2);
}}
.tl-action-go {{
  display: block;
  font-size: 14px;
  font-weight: 500;
  color: var(--tl-action);
}}

/* === STREAMLIT CHROME ===
   Config-first: deploy button / dev toolbar hidden via
   client.toolbarMode = "minimal" in .streamlit/config.toml (documented
   option, valid on pinned 1.50.0). Intentionally NO CSS rules for
   stToolbar / stDecoration / metric-container — those selectors are not
   proven in this repo. */

/* === INLINE CODE (markdown) ===
   Streamlit's default renders code spans red — red is reserved for errors.
   Ink on mist: the mono face already separates code from prose, so the
   span does not need a hue as well. */
[data-testid="stAppViewContainer"] code {{
  color: var(--tl-ink);
  background: var(--tl-mist);
  border-radius: 4px;
}}

/* === FOCUS ===
   One visible ring everywhere, on both surface families. Focus is never
   removed; keyboard users navigate the whole product. */
[data-testid="stAppViewContainer"] :focus-visible {{
  outline: 2px solid var(--tl-action);
  outline-offset: 2px;
  border-radius: 2px;
}}
[data-testid="stSidebar"] :focus-visible {{
  outline: 2px solid var(--tl-focus);
  outline-offset: 2px;
}}

/* === AI REVIEW BODY (Insights & Review) ===
   The model's markdown ## / ### headings must sit BELOW the page's
   section titles — inside the keyed tl_review_* containers they
   render at body-plus scale instead of full H2/H3 size. */
[class*="st-key-tl_review_"] h1,
[class*="st-key-tl_review_"] h2,
[class*="st-key-tl_review_"] h3 {{
  font-size: 1.05rem;
  font-weight: 600;
  padding-top: var(--tl-space-4);
  padding-bottom: 0;
}}

/* A weekly review is several hundred words of prose sitting in a full-width
   app column. Unmeasured, it reads as a wall and gets skimmed — which
   defeats the point of writing it. 68ch is the readable measure; the
   paragraph spacing gives the sections somewhere to breathe. */
[class*="st-key-tl_review_"] p,
[class*="st-key-tl_review_"] li {{
  max-width: 68ch;
  line-height: 1.65;
}}
[class*="st-key-tl_review_"] p {{
  margin-bottom: var(--tl-space-3);
}}
[class*="st-key-tl_review_"] ul,
[class*="st-key-tl_review_"] ol {{
  margin-bottom: var(--tl-space-3);
}}
[class*="st-key-tl_review_"] li {{
  margin-bottom: var(--tl-space-2);
}}

/* === TRADE CALENDAR (dashboard month view) ===
   Flat outcome dots — green net-positive, red net-negative, muted gray
   breakeven — replacing emoji markers. The outcome rides in the widget
   key, so the st-key-… container class carries it; the descendant
   selector tolerates the tooltip wrapper around buttons with help=. */
[class*="st-key-calday_"] button::before {{
  content: '';
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: var(--tl-radius-full);
  margin-right: 6px;
  vertical-align: 1px;
  background: var(--tl-muted);
}}
[class*="st-key-calday_"][class*="_positive"] button::before {{
  background: var(--tl-success-ink);
}}
[class*="st-key-calday_"][class*="_negative"] button::before {{
  background: var(--tl-danger-ink);
}}
.tl-cal-legend {{
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--tl-space-4);
  font-size: 12px;
  color: var(--tl-muted);
  margin: var(--tl-space-2) 0 var(--tl-space-3) 0;
}}
.tl-cal-key {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
}}
.tl-cal-dot {{
  width: 7px;
  height: 7px;
  border-radius: var(--tl-radius-full);
  background: var(--tl-muted);
  display: inline-block;
}}
.tl-cal-dot.positive {{ background: var(--tl-success-ink); }}
.tl-cal-dot.negative {{ background: var(--tl-danger-ink); }}

/* === MOTION (accessibility — PRODUCT.md) ===
   Reduced motion means fewer and gentler, not zero: color feedback that
   aids comprehension stays, movement goes. Nothing here translates or
   scales, so removing transitions entirely is the correct reduction. */
@media (prefers-reduced-motion: reduce) {{
  .tl-action-card,
  .stButton > button,
  .stFormSubmitButton > button,
  .tl-table td,
  .tl-mobile-nav-item,
  [data-testid="stSidebar"] a,
  [data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] {{
    transition: none;
  }}
  /* Colour feedback stays; the movement goes. */
  .tl-mobile-nav-item:active,
  .st-key-tl_nav_action [data-testid="stPageLink-NavLink"]:active {{
    transform: none;
  }}
  [class*="st-key-tl_step_"] {{
    animation: none;
  }}
}}

/* === MOBILE (SP4 Phase B, <=640px) ===
   Streamlit stacks its own widgets, but our custom HTML does not: flex
   rows and HTML tables need explicit reflow. The KPI strip becomes a
   two-column compact list rather than six full-width rows, tables scroll
   inside their own frame, and touch targets reach >=44px. */
@media (max-width: 640px) {{
  /* The bottom bar appears only here, and reserves its own height plus the
     gesture-bar inset so it never covers the last row of a table. */
  .tl-mobile-nav {{
    display: flex;
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 100;
    background: var(--tl-rail);
    border-top: 1px solid var(--tl-border);
    padding-bottom: env(safe-area-inset-bottom, 0px);
  }}
  .tl-mobile-nav-item {{ position: relative; }}
  [data-testid="stAppViewContainer"] .block-container {{
    padding-bottom: calc(72px + env(safe-area-inset-bottom, 0px));
  }}
  /* The numbered rail wraps into two rows of circles at this width; the
     masthead's "Step N of 5" carries the position instead. */
  .tl-wizard-progress {{ display: none; }}
  /* Clear the bottom navigation so the wizard's primary action is never
     underneath it. */
  .st-key-tl_wizard_bar {{
    bottom: calc(51px + env(safe-area-inset-bottom, 0px));
  }}
  .tl-kpi-row {{ flex-direction: column; gap: var(--tl-space-2); }}
  .tl-kpi-card {{ width: 100%; }}
  .tl-kpi-cell {{ flex: 1 1 50%; }}
  .tl-kpi-cell:nth-child(odd) {{ border-left-width: 0; }}
  .tl-kpi-cell:nth-child(n+3) {{ border-top: 1px solid var(--tl-hairline); }}
  .tl-kpi-figure {{ font-size: 22px; line-height: 28px; }}
  .tl-masthead {{ align-items: flex-start; flex-direction: column; gap: var(--tl-space-2); }}
  .tl-masthead-title {{ font-size: 24px; line-height: 30px; }}
  .tl-finding {{ flex-direction: column; gap: var(--tl-space-2); }}
  .tl-table-wrap {{ overflow-x: auto; -webkit-overflow-scrolling: touch; }}
  .tl-table {{ min-width: 560px; }}
  .stButton > button,
  .stFormSubmitButton > button {{ min-height: 44px; }}
  [data-testid="stTextInput"] input {{ min-height: 44px; }}
}}
</style>"""


def inject_design_system() -> None:
    """Inject the design-system CSS. Call once per page, after
    ``theme.inject_css()``.

    Re-injects on every script run (Streamlit clears un-rendered elements
    each rerun — see module docstring for why the spec's skip-flag would
    break styling). The session flag is kept as an introspection marker.
    """
    import streamlit as st  # lazy: keep module import Streamlit-free

    st.markdown(build_css(), unsafe_allow_html=True)
    st.session_state["_tl_css_injected"] = True


# =========================================================================
# FORMATTERS (shared by KPI card)
# =========================================================================


def _fmt_currency(value: float) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


def _fmt_value(value: Optional[float], format: str) -> str:
    """Format a KPI value. None → 'N/A' (never '--', never '0')."""
    if value is None:
        return "N/A"
    if format == "currency":
        return _fmt_currency(float(value))
    if format == "percent":
        return f"{float(value):.1f}%"
    if format == "number":
        return f"{float(value):,.0f}"
    if format == "ratio":
        if math.isinf(float(value)):
            return "∞"
        return f"{float(value):.1f}x"
    return escape(str(value))


def _sign_class(value: Optional[float]) -> str:
    if value is None:
        return "missing"
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return ""


# =========================================================================
# HTML FACTORIES — each returns a string for
# st.markdown(html, unsafe_allow_html=True)
# =========================================================================


def render_kpi_card(
    label: str,
    value: Optional[float],
    delta: Optional[float] = None,
    format: str = "currency",
) -> str:
    """KPI card. Sign coloring applies to currency (and delta); zero is
    neutral; missing values render 'N/A' in muted color."""
    text = _fmt_value(value, format)
    cls = _sign_class(value) if format == "currency" else ""
    if value is None:
        cls = "missing"
    delta_html = ""
    if delta is not None:
        arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "")
        delta_html = (
            f'<div class="tl-kpi-delta {_sign_class(delta)}">'
            f"{arrow} {_fmt_value(delta, format)}</div>"
        )
    return (
        '<div class="tl-kpi-card">'
        f'<div class="tl-kpi-label">{escape(label)}</div>'
        f'<div class="tl-kpi-value {cls}">{text}</div>'
        f"{delta_html}</div>"
    )


def render_badge(text: str, variant: str) -> str:
    """Pill badge. Unknown variants fall back to neutral (never raises in
    a render path). Confidence variants map to tl-confidence-* classes."""
    if variant not in _BADGE_VARIANTS:
        variant = "neutral"
    if variant.startswith("confidence-"):
        cls = f"tl-{variant}"
    else:
        cls = f"tl-badge-{variant}"
    return f'<span class="tl-badge {cls}">{escape(str(text))}</span>'


def confidence_badge(confidence: float) -> str:
    """Confidence % badge. >= 0.70 high (teal-free green), >= 0.40 medium,
    else low/neutral. Red is never used for confidence (errors only)."""
    if confidence >= 0.70:
        tier = "confidence-high"
    elif confidence >= 0.40:
        tier = "confidence-medium"
    else:
        tier = "confidence-low"
    return render_badge(f"{confidence:.0%}", tier)


def render_insight_card(
    icon: str,
    title: str,
    body: str,
    evidence: str,
    confidence: float,
    variant: str = "neutral",
) -> str:
    """Insight card. Variant is expressed via tinted background and accent
    icon color — no colored side borders (PRODUCT.md anti-pattern)."""
    if variant not in _INSIGHT_VARIANTS:
        variant = "neutral"
    return (
        f'<div class="tl-insight-card {variant}">'
        '<div class="tl-insight-head">'
        f'<span class="tl-insight-icon">{escape(icon)}</span>'
        f'<span class="tl-insight-title">{escape(title)}</span>'
        f"{confidence_badge(confidence)}"
        "</div>"
        f'<p class="tl-insight-body">{escape(body)}</p>'
        f'<p class="tl-insight-evidence">Evidence: {escape(evidence)}</p>'
        "</div>"
    )


def render_next_step(
    label: str, completed: int, total: int, trades_remaining: int = 0
) -> str:
    """One next action for a trader who hasn't reached their first review.

    Deliberately a single step rather than a checklist: a list of everything
    not yet done reads as a chore, and the only thing that helps is the one
    action available right now.
    """
    detail = (
        f"{trades_remaining} more completed "
        f"{'trade' if trades_remaining == 1 else 'trades'} to unlock it."
        if trades_remaining
        else "Takes a couple of minutes."
    )
    return (
        '<div class="tl-next-step">'
        f'<div class="tl-next-step-count">{completed} of {total} done</div>'
        f'<div class="tl-next-step-label">{escape(label)}</div>'
        f'<div class="tl-next-step-detail">{escape(detail)}</div>'
        "</div>"
    )


def render_empty_state(
    icon: str,
    title: str,
    body: str,
    action_label: Optional[str] = None,
    image_path: Optional[str] = None,
) -> str:
    """Empty-state card. ``image_path`` is an asset filename resolved via
    ``get_asset_as_base64``; a raw base64 string is also accepted (used
    when the caller already encoded the image)."""
    img_html = ""
    if image_path:
        b64 = get_asset_as_base64(image_path)
        if not b64 and len(image_path) > 256:
            b64 = image_path  # caller passed raw base64 content
        if b64:
            img_html = (
                f'<img class="tl-empty-img" alt="" '
                f'src="data:image/png;base64,{b64}"/>'
            )
    action_html = (
        f'<div class="tl-empty-action">{escape(action_label)}</div>'
        if action_label
        else ""
    )
    return (
        '<div class="tl-empty-card">'
        f"{img_html}"
        f'<div class="icon">{escape(icon)}</div>'
        f"<h4>{escape(title)}</h4>"
        f"<p>{escape(body)}</p>"
        f"{action_html}</div>"
    )


def render_banner(text: str, variant: str = "warning") -> str:
    """Inline banner: warning | info | danger. Unknown variants fall back
    to warning (visible but non-alarming)."""
    if variant not in _BANNER_VARIANTS:
        variant = "warning"
    return f'<div class="tl-banner tl-banner-{variant}">{escape(text)}</div>'


def render_section_header(title: str, subtitle: Optional[str] = None) -> str:
    """Section break. Delegates to ``components/workspace.py``, which owns
    the markup for every shared workspace primitive — this and
    ``components/ui.section_header`` were byte-identical copies."""
    return _render_section_header(title, subtitle)


def render_ai_card(content_html: str) -> str:
    """AI-output card with the 'AI' corner tag. ``content_html`` is trusted
    caller-built HTML (escape any user text BEFORE composing it)."""
    return f'<div class="tl-ai-card">{content_html}</div>'


def render_chip_row(chips: list, color_map: Optional[dict] = None) -> str:
    """Row of chips. ``color_map`` maps chip text → badge variant;
    default variant is neutral."""
    color_map = color_map or {}
    badges = "".join(
        render_badge(chip, color_map.get(chip, "neutral")) for chip in chips
    )
    return f'<div class="tl-chip-row">{badges}</div>'


def render_step_indicator(current_step: int, steps: list) -> str:
    """Wizard stepper. ``current_step`` is 1-indexed. Steps before it are
    done (✓), the current one is active, later ones are future. Connector
    i (after step i) is teal once step i is done."""
    parts = ['<div class="tl-stepper">']
    total = len(steps)
    for i, label in enumerate(steps, start=1):
        if i < current_step:
            state, content = "done", "✓"
        elif i == current_step:
            state, content = "active", str(i)
        else:
            state, content = "future", str(i)
        parts.append(
            '<div class="tl-step">'
            f'<div class="tl-step-circle {state}">{content}</div>'
            f'<div class="tl-step-label">{escape(str(label))}</div>'
            "</div>"
        )
        if i < total:
            seg = "done" if i < current_step else "future"
            parts.append(f'<div class="tl-step-connector {seg}"></div>')
    parts.append("</div>")
    return "".join(parts)


@lru_cache(maxsize=32)
def _read_asset_b64(path_str: str) -> str:
    with open(path_str, "rb") as fh:
        return base64.b64encode(fh.read()).decode("ascii")


def get_asset_as_base64(filename: str) -> str:
    """Read ``src/tradelens/ui/assets/<filename>`` as base64.

    Returns "" silently if the file is missing or unreadable — pages must
    degrade gracefully when an asset hasn't been generated yet. Only
    successful reads are cached, so assets added later are picked up.
    """
    path = ASSETS_DIR / filename
    try:
        if not path.is_file():
            return ""
        return _read_asset_b64(str(path))
    except OSError:
        return ""
