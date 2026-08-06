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
# COLOR TOKENS — one tonal-dark theme
# =========================================================================
# The signed-in product runs ONE theme on ONE surface family. There is no
# toggle and no light workspace; a view is dark because the whole product is.
#
# This replaces a hybrid that carried two live colour systems at once — a
# light workspace and a duplicate legacy dark set — which is how the same
# concept ended up with two names and two values (spec D1). The retarget does
# not reuse a name whose meaning changes: superseded names are DELETED, never
# aliased, so a missed call site raises ImportError instead of silently
# flipping meaning (spec D2). Every pair below is contrast-tested in
# tests/test_dark_workspace.py, not asserted from the specification.
# -------------------------------------------------------------------------
# SEMANTIC RAMP (values unchanged — these were never superseded)
# -------------------------------------------------------------------------
TL_PRIMARY = "#00e5cc"
TL_PRIMARY_HOVER = "#33ecd8"
TL_PRIMARY_DIM = "rgba(0,229,204,0.12)"
TL_SUCCESS = "#22c55e"
TL_SUCCESS_DIM = "rgba(34,197,94,0.12)"
TL_DANGER = "#f56565"
TL_DANGER_DIM = "rgba(245,101,101,0.12)"
TL_WARNING = "#f59e0b"
TL_WARNING_DIM = "rgba(245,158,11,0.12)"
TL_NEUTRAL = "#374151"
TL_NEUTRAL_DIM = "rgba(55,65,81,0.3)"
TL_FOCUS = "#00E5CC"  # active marks on dark surfaces (== TL_PRIMARY)

# -------------------------------------------------------------------------
# ROLE SYSTEM — one name, one meaning
# -------------------------------------------------------------------------
# Surfaces separate by only 1.02–1.09:1. That is correct for tonal design and
# must NOT be "fixed" by pushing them apart, which produces the
# dark-cards-on-dark-cards effect the direction forbids. The consequence is a
# hard rule: surface tone may never be the only thing separating two regions.
# Every boundary that carries meaning is drawn with TL_LINE_HAIRLINE, or
# TL_LINE_STRONG where the boundary is load-bearing (spec D4).
TL_SURFACE_CANVAS = "#091216"  # quiet page background
TL_SURFACE_RAIL = "#071014"  # deepest structural surface
TL_SURFACE_PANEL = "#101B20"  # tables, filters, forms, composed sections
TL_SURFACE_ELEVATED = "#152329"  # selected controls, overlays, readouts
TL_SURFACE_CHART = "#0C181D"  # Plotly stage
TL_SURFACE_FIELD = "#122026"  # inputs and selectors

TL_CONTENT_PRIMARY = "#ECF5F4"  # 14.52–17.32:1 across the six surfaces
TL_CONTENT_SECONDARY = "#91A3A7"  # 6.13–7.32:1 across the six surfaces

TL_LINE_HAIRLINE = "#26373D"  # structure without card-box noise
# The specification first proposed #3A4E56. Measured, it is 1.84–2.20:1 across
# the six surfaces — below the 3:1 floor a non-text boundary needs, and it
# would have failed this module's own contract test. #5C6E77 is the smallest
# value on the same cool blue-grey ramp clearing 3:1 on all six, with
# ELEVATED the binding case at 3.03:1 because the Partner drawer's edge sits
# there. Corrected in the specification as amendment C6.
TL_LINE_STRONG = "#5C6E77"  # load-bearing boundaries; >=3:1 on every surface

TL_ACCENT_ACTION = TL_PRIMARY  # unchanged bright TradeLens teal

# Grade scale (A → F): success green through amber to danger red. Grade chips
# are read on the dark panel now that the light PAPER surface is gone, so the
# ramp uses the dark semantic family with brighter lime and orange
# intermediates. Every step clears 4.5:1 on TL_SURFACE_PANEL.
TL_GRADE_A = TL_SUCCESS
TL_GRADE_B = "#A3E635"
TL_GRADE_C = TL_WARNING
TL_GRADE_D = "#FB923C"
TL_GRADE_F = TL_DANGER

# =========================================================================
# Z-INDEX SCALE
# =========================================================================
# There was no scale before this: three arbitrary literals (1000, 20, 100) and
# zero tokens (spec D13). Navigation always outranks the Partner, because a
# trader must never dismiss a chat surface to reach navigation, and blocking
# confirmations outrank everything. No module may declare a raw z-index
# outside this scale — 1000 in particular is how the next overlay ends up
# at 1001.
TL_Z_BASE = 0
TL_Z_RAISED = 10  # sticky section and table headers
TL_Z_PARTNER = 20  # AI Partner launcher and drawer
TL_Z_NAV = 30  # navigation rail, bottom nav
TL_Z_SHEET = 40  # mobile More sheet
TL_Z_OVERLAY = 50  # blocking confirmations

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
# A figure paints its own stage rather than inheriting whatever surface
# frames it. That mattered when the workspace was light and still does: the
# chart stage is a distinct surface from the canvas and the panel, so a
# figure that inherited would sit on whichever one happened to frame it and
# the bright semantic ramp would lose the dark ground it needs.
#
# The stage is set here, on the template, because design_system.py is the
# single source of truth for chart theming. Task 6 may centralise a
# `apply_chart_stage` wrapper and the framing radius/padding on top of it;
# the colour contract lives here either way.
PLOTLY_TEMPLATE = go.layout.Template(
    layout=go.Layout(
        paper_bgcolor=TL_SURFACE_CHART,
        plot_bgcolor=TL_SURFACE_CHART,
        font=dict(family=TL_FONT_BODY, color=TL_CONTENT_PRIMARY, size=12),
        title=dict(font=dict(size=14, color=TL_CONTENT_PRIMARY), x=0.0, xanchor="left"),
        # Six marks that stay separable on the stage. The sixth was
        # TL_NEUTRAL, a near-black surface grey that measures 1.71:1 here —
        # it was a background token doing duty as a data colour. TL_CONTENT_PRIMARY is
        # the light end of the neutral ramp and reads clearly against the
        # mid grey already at position four.
        colorway=[
            TL_PRIMARY,
            TL_WARNING,
            TL_SUCCESS,
            TL_CONTENT_SECONDARY,
            TL_DANGER,
            TL_CONTENT_PRIMARY,
        ],
        # automargin: once the figure paints its own stage, the stage has a
        # visible edge and pinned page margins clip the tick labels against
        # it. Letting each axis reserve what its labels need fixes every
        # chart at once instead of tuning margins per call site.
        xaxis=dict(
            gridcolor=TL_LINE_HAIRLINE,
            zerolinecolor=TL_LINE_HAIRLINE,
            automargin=True,
            tickfont=dict(color=TL_CONTENT_SECONDARY, size=11),
            title=dict(font=dict(color=TL_CONTENT_SECONDARY, size=12)),
        ),
        yaxis=dict(
            gridcolor=TL_LINE_HAIRLINE,
            zerolinecolor=TL_LINE_HAIRLINE,
            automargin=True,
            tickfont=dict(color=TL_CONTENT_SECONDARY, size=11),
            title=dict(font=dict(color=TL_CONTENT_SECONDARY, size=12)),
        ),
        legend=dict(
            bgcolor="rgba(0,0,0,0)",
            font=dict(color=TL_CONTENT_SECONDARY, size=11),
        ),
        hoverlabel=dict(
            bgcolor=TL_SURFACE_ELEVATED,
            bordercolor=TL_LINE_HAIRLINE,
            font=dict(family=TL_FONT_MONO, color=TL_CONTENT_PRIMARY, size=12),
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
  /* -- surfaces: one family, separated by lines not by tone -- */
  --tl-surface-canvas: {TL_SURFACE_CANVAS};
  --tl-surface-rail: {TL_SURFACE_RAIL};
  --tl-surface-panel: {TL_SURFACE_PANEL};
  --tl-surface-elevated: {TL_SURFACE_ELEVATED};
  --tl-surface-chart: {TL_SURFACE_CHART};
  --tl-surface-field: {TL_SURFACE_FIELD};
  /* -- content -- */
  --tl-content-primary: {TL_CONTENT_PRIMARY};
  --tl-content-secondary: {TL_CONTENT_SECONDARY};
  /* -- structure -- */
  --tl-line-hairline: {TL_LINE_HAIRLINE};
  --tl-line-strong: {TL_LINE_STRONG};
  --tl-accent-action: {TL_ACCENT_ACTION};
  --tl-rule: {TL_RULE};
  /* -- layering: nav always outranks the Partner -- */
  --tl-z-base: {TL_Z_BASE}; --tl-z-raised: {TL_Z_RAISED};
  --tl-z-partner: {TL_Z_PARTNER}; --tl-z-nav: {TL_Z_NAV};
  --tl-z-sheet: {TL_Z_SHEET}; --tl-z-overlay: {TL_Z_OVERLAY};
  /* -- semantic ramp -- */
  --tl-focus: {TL_FOCUS};
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
  background: var(--tl-surface-canvas);
  font-family: var(--tl-font-ui);
  color: var(--tl-content-primary);
}}
/* Schibsted sets titles only — used everywhere it becomes texture. */
[data-testid="stAppViewContainer"] h1,
[data-testid="stAppViewContainer"] h2,
[data-testid="stAppViewContainer"] h3 {{
  font-family: var(--tl-font-display);
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--tl-content-primary);
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

/* === SIDEBAR — the architectural rail ===
   The rail is the deepest surface in the product, but only just: measured,
   it separates from the canvas at 1.02:1, which no eye resolves. Tone cannot
   carry this boundary, so the edge is drawn — and drawn with the STRONG line,
   not the hairline, because this is the one structural division on every
   screen. Hairlines divide things that belong together; this separates
   navigation from work. */
[data-testid="stSidebar"] {{
  background: var(--tl-surface-rail);
  border-right: 1px solid var(--tl-line-strong);
  color: var(--tl-content-primary);
}}
[data-testid="stSidebar"] a,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {{
  color: var(--tl-content-primary);
}}
/* Nav links (st.page_link renders an anchor): quiet rest state, surface
   hover, visible keyboard focus. */
[data-testid="stSidebar"] a {{
  border-radius: var(--tl-radius-sm);
  transition: background var(--tl-dur-state) var(--tl-ease-out);
}}
@media (hover: hover) and (pointer: fine) {{
  [data-testid="stSidebar"] a:hover {{
    background: var(--tl-surface-elevated);
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
  color: var(--tl-content-primary);
  position: relative;
  transition: background var(--tl-dur-state) var(--tl-ease-out);
}}
@media (hover: hover) and (pointer: fine) {{
  [data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover {{
    background: var(--tl-surface-elevated);
  }}
}}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:focus-visible {{
  outline: 2px solid var(--tl-focus);
  outline-offset: -2px;
}}
/* Press feedback only — these rows are visited dozens of times a session,
   so nothing here is allowed to take time to finish. */
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:active {{
  background: var(--tl-surface-elevated);
}}

/* --- the current destination ---
   Three cues, none of them colour on its own: a teal indicator bar, a
   heavier label, and a raised surface. */
[class*="st-key-tl_nav_"][class*="_active"] [data-testid="stPageLink-NavLink"] {{
  background: var(--tl-surface-elevated);
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
  color: var(--tl-surface-rail);
  font-weight: 600;
  justify-content: center;
  transition: opacity var(--tl-dur-state) var(--tl-ease-out),
              transform var(--tl-dur-press) var(--tl-ease-out);
}}
/* The link sets dark-on-teal, but Streamlit renders the label as a <p>
   inside a markdown container, and the rail's own text rule repaints that
   <p> near-white — 1.33:1 on the brightest surface in the product, on its
   single most prominent action. Every descendant inherits the link.

   UNCONDITIONAL, and deliberately outside the hover query below: legibility
   is not a hover state. Nested inside it, the label stayed near-white on
   every touch device, and a desktop browser merely resized to 375px would
   never show it — `hover: hover` still matches when you only change the
   viewport. */
.st-key-tl_nav_action [data-testid="stPageLink-NavLink"] *,
.st-key-tl_nav_action [data-testid="stPageLink-NavLink"] p {{
  color: inherit;
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
  color: var(--tl-content-secondary);
}}

/* --- tablet: a narrower rail, same hierarchy --- */
@media (min-width: 768px) and (max-width: 1023px) {{
  [data-testid="stSidebar"] {{ width: 208px; min-width: 208px; }}
  [data-testid="stAppViewContainer"] .block-container {{
    padding-left: var(--tl-space-4);
    padding-right: var(--tl-space-4);
  }}
}}

/* --- keyboard bypass ---
   Off-canvas until focused; it appears immediately rather than animating
   focus, then moves focus to the content anchor before each page masthead. */
.tl-skip-shell {{
  height: 0;
  overflow: visible;
}}
[data-testid="stAppViewContainer"] a.tl-skip-link {{
  position: fixed;
  top: var(--tl-space-2);
  left: var(--tl-space-2);
  /* Overlay tier, not nav: a skip link that the rail can occlude is a skip
     link that does not work. It was 1000 — above everything — and must keep
     that standing inside the scale. */
  z-index: var(--tl-z-overlay);
  transform: translateY(calc(-100% - var(--tl-space-4)));
  min-height: 44px;
  padding: 0 var(--tl-space-3);
  display: inline-flex;
  align-items: center;
  border-radius: var(--tl-radius-sm);
  background: var(--tl-surface-rail);
  /* --tl-rail-ink was never defined, so this inherited: dark ink on a
     near-black rail, i.e. an invisible skip link. Pre-existing; caught by the
     dangling-variable guard this task adds. */
  color: var(--tl-content-primary);
  text-decoration: none;
  font-weight: 700;
}}
[data-testid="stAppViewContainer"] a.tl-skip-link:focus-visible {{
  transform: none;
  outline: 2px solid var(--tl-focus);
  outline-offset: 2px;
}}
.tl-main-anchor {{
  position: relative;
  display: block;
  scroll-margin-top: var(--tl-space-4);
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
  color: var(--tl-content-secondary);
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

/* --- More: the fifth slot ---
   A native <details>. The summary IS the fifth tab, so it inherits every
   tab rule above — including the 44px floor and the active indicator — and
   the marker is removed because the tab is already labelled. */
.tl-mobile-more {{
  flex: 1 1 0;
  position: relative;
}}
.tl-mobile-more > summary {{
  list-style: none;
  cursor: pointer;
}}
.tl-mobile-more > summary::-webkit-details-marker {{ display: none; }}
.tl-mobile-more > summary::marker {{ content: ''; }}

/* A closed <details> normally collapses its content out of the layout, but
   an absolutely positioned child escapes that: the sheet stayed invisible
   and still TABBABLE, so a keyboard user hit three links inside a shut
   menu. Closed means gone, for the pointer and the keyboard alike. */
.tl-mobile-more:not([open]) > .tl-mobile-more-sheet {{
  display: none;
}}

/* The sheet rises from the bar rather than pushing it, so the four tabs
   never move under a thumb that is already reaching for them. */
.tl-mobile-more-sheet {{
  position: absolute;
  bottom: 100%;
  right: 0;
  min-width: 208px;
  background: var(--tl-surface-rail);
  border: 1px solid var(--tl-line-hairline);
  border-radius: var(--tl-radius-md) var(--tl-radius-md) 0 0;
  padding: var(--tl-space-2);
  box-shadow: var(--tl-shadow);
}}
[data-testid="stAppViewContainer"] a.tl-mobile-more-item,
.tl-mobile-more-item {{
  display: flex;
  align-items: center;
  gap: var(--tl-space-3);
  min-height: 44px;
  padding: 0 var(--tl-space-3);
  border-radius: var(--tl-radius-sm);
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
  color: var(--tl-content-primary);
}}
.tl-mobile-more-icon {{
  font-family: 'Material Symbols Rounded';
  font-size: 20px;
  line-height: 1;
  font-weight: 300;
}}
[data-testid="stAppViewContainer"] a.tl-mobile-more-item.is-active,
.tl-mobile-more-item.is-active {{
  color: var(--tl-focus);
}}
/* Settings stays the quiet utility here too: muted, and set below a rule
   rather than reading as a third piece of work. */
[data-testid="stAppViewContainer"] a.tl-mobile-more-item.is-quiet,
.tl-mobile-more-item.is-quiet {{
  color: var(--tl-content-secondary);
  font-weight: 400;
  margin-top: var(--tl-space-2);
  padding-top: var(--tl-space-2);
  border-top: 1px solid var(--tl-line-hairline);
  border-radius: 0;
}}

/* Opening More is a state change worth conveying: a panel that appears
   from nothing over a fixed bar reads as a glitch. 160ms — the short end of
   the range, because this is a menu a thumb is already moving through —
   opacity and a 4px rise only, on the shared curve. Nothing else here
   moves, and the tabs themselves never animate: they are hit dozens of
   times a session. */
@media (prefers-reduced-motion: no-preference) {{
  .tl-mobile-more[open] > .tl-mobile-more-sheet {{
    animation: tl-more-in 160ms var(--tl-ease-out) both;
  }}
  @keyframes tl-more-in {{
    from {{ opacity: 0; transform: translateY(4px); }}
    to {{ opacity: 1; transform: none; }}
  }}
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
  color: var(--tl-content-primary);
}}
.tl-side-brand-sub {{
  color: var(--tl-content-secondary);
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  margin: 2px 0 var(--tl-space-3) 28px;
}}
.tl-side-note {{
  border: 1px solid var(--tl-line-hairline);
  background: var(--tl-surface-elevated);
  border-radius: var(--tl-radius-sm);
  padding: var(--tl-space-2) var(--tl-space-3);
  margin: var(--tl-space-3) 0;
  font-size: 12px;
  line-height: 1.45;
  color: var(--tl-content-secondary);
}}
.tl-side-note b {{
  color: var(--tl-content-primary);
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
  background: var(--tl-surface-panel);
  border: 1px solid var(--tl-line-hairline);
  border-radius: var(--tl-radius-md);
  padding: 12px 16px;
}}
.stMetric [data-testid="stMetricValue"] {{
  font-family: var(--tl-font-mono);
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  color: var(--tl-content-primary);
}}
.stMetric [data-testid="stMetricDelta"] {{
  font-family: var(--tl-font-mono);
}}
.stMetric [data-testid="stMetricLabel"] {{
  color: var(--tl-content-secondary);
}}

/* === BUTTONS (all states: rest, hover, focus, active) ===
   Form submit buttons (Sign In, Save Trade, …) are primary actions too —
   they get the identical treatment as .stButton. */
.stButton > button,
.stFormSubmitButton > button {{
  background: var(--tl-accent-action);
  color: var(--tl-surface-panel);
  border: 1px solid var(--tl-accent-action);
  border-radius: var(--tl-radius-sm);
  font-family: var(--tl-font-ui);
  font-weight: 500;
  transition: background var(--tl-dur-state) var(--tl-ease-out),
              border-color var(--tl-dur-state) var(--tl-ease-out);
}}
@media (hover: hover) and (pointer: fine) {{
  .stButton > button:hover,
  .stFormSubmitButton > button:hover {{
    background: var(--tl-primary-hover);
    border-color: var(--tl-primary-hover);
  }}
}}
.stButton > button:focus-visible,
.stFormSubmitButton > button:focus-visible {{
  outline: 2px solid var(--tl-accent-action);
  outline-offset: 2px;
}}
.stButton > button:active,
.stFormSubmitButton > button:active {{
  background: var(--tl-primary-hover);
}}
/* The rail holds exactly ONE filled action — "Log completed trade". Sign
   out is a utility control, so it is outlined: two filled teal buttons in
   one column read as two primaries and the eye cannot tell which matters. */
[data-testid="stSidebar"] .stButton > button {{
  background: transparent;
  border-color: var(--tl-line-hairline);
  color: var(--tl-content-primary);
  min-height: 44px;
}}
@media (hover: hover) and (pointer: fine) {{
  [data-testid="stSidebar"] .stButton > button:hover {{
    background: var(--tl-surface-elevated);
    border-color: var(--tl-content-secondary);
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
  color: var(--tl-content-primary);
  border-color: var(--tl-line-hairline);
}}
@media (hover: hover) and (pointer: fine) {{
  [class*="st-key-secondary_"] button:hover {{
    background: var(--tl-surface-elevated);
    border-color: var(--tl-content-secondary);
  }}
}}
[class*="st-key-secondary_"] button:active {{
  background: var(--tl-surface-elevated);
}}
/* Outlined buttons had no focus rule of their own and fell through to
   Streamlit's default ring. Measured by tabbing through 26 controls, that
   default is adequate — this is NOT fixing an invisible ring. It pins the
   ring to our own token, so the one state that may never be quiet does not
   depend on a framework default that can change between releases. Spec 4.6
   requires TL_ACCENT_ACTION specifically. */
[class*="st-key-secondary_"] button:focus-visible {{
  outline: 2px solid var(--tl-focus);
  outline-offset: 2px;
}}
/* ...and the same for Streamlit's OWN button variants. Our `secondary_` key
   convention only covers buttons we name; st.button(type="secondary")
   renders stBaseButton-secondary whatever its key. Same reasoning as above:
   the framework default measured fine, and this makes the token explicit
   rather than inherited. */
[data-testid="stBaseButton-primary"]:focus-visible,
[data-testid="stBaseButton-secondary"]:focus-visible,
[data-testid="stBaseButton-secondaryFormSubmit"]:focus-visible,
[data-testid="stBaseButton-elementToolbar"]:focus-visible {{
  outline: 2px solid var(--tl-focus);
  outline-offset: 2px;
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
  border-bottom: 1px solid var(--tl-line-hairline);
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
  color: var(--tl-content-secondary);
  margin: 0 0 var(--tl-space-1) 0;
}}
/* === PAGE CHROME TYPE, ANCHORED ===
   These four carried a single class, so Streamlit's markdown stylesheet
   (a 0,1,1 container selector) decided their size instead: the masthead
   title declared 30px and rendered 44, the section title declared 22 and
   rendered 36, the subtitle declared 14 and rendered 16. The phone override
   declared 24px and never applied at all. Anchoring them to
   the app container puts the design system back in control.

   The VALUES here are the ones that shipped and were approved across six
   pages, transcribed so declaration and rendering finally agree — not a new
   scale. Changing the scale is a visual decision, and a separate one. */
[data-testid="stAppViewContainer"] .tl-masthead-title {{
  font-family: var(--tl-font-display);
  font-size: 44px;
  line-height: 50px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--tl-content-primary);
  margin: 0;
}}
[data-testid="stAppViewContainer"] .tl-masthead-subtitle {{
  font-size: 16px;
  line-height: 20px;
  color: var(--tl-content-secondary);
  margin: var(--tl-space-1) 0 0 0;
  max-width: 68ch;
}}
.tl-masthead-meta {{
  font-family: var(--tl-font-mono);
  font-size: 12px;
  line-height: 18px;
  color: var(--tl-content-secondary);
  margin: 0;
  white-space: nowrap;
}}

/* --- ruled KPI strip ---
   One measurement across a period, divided by hairlines. Six boxed tiles
   would say these numbers are six separate things; they are not. */
.tl-kpi-strip {{
  display: flex;
  flex-wrap: wrap;
  background: var(--tl-surface-panel);
  border: 1px solid var(--tl-line-hairline);
  border-radius: var(--tl-radius-md);
  margin-bottom: var(--tl-space-6);
}}
.tl-kpi-cell {{
  flex: 1 1 150px;
  min-width: 0;
  padding: var(--tl-space-3) var(--tl-space-4);
}}
.tl-kpi-cell + .tl-kpi-cell {{
  border-left: 1px solid var(--tl-line-hairline);
}}
.tl-kpi-key {{
  font-size: 12px;
  line-height: 18px;
  font-weight: 500;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--tl-content-secondary);
  margin: 0;
}}
.tl-kpi-figure {{
  font-family: var(--tl-font-mono);
  font-variant-numeric: tabular-nums;
  font-size: 28px;
  line-height: 34px;
  font-weight: 500;
  letter-spacing: -0.02em;
  color: var(--tl-content-primary);
  margin: var(--tl-space-1) 0 0 0;
}}
.tl-kpi-cell.tone-positive .tl-kpi-figure {{ color: var(--tl-success); }}
.tl-kpi-cell.tone-negative .tl-kpi-figure {{ color: var(--tl-danger); }}
.tl-kpi-cell.tone-warning .tl-kpi-figure {{ color: var(--tl-warning); }}
.tl-kpi-detail {{
  font-family: var(--tl-font-mono);
  font-size: 12px;
  line-height: 18px;
  color: var(--tl-content-secondary);
  margin: var(--tl-space-1) 0 0 0;
}}

/* --- EVIDENCE RAIL: the signature ---
   A margin annotation, not a card: neutral rule, indented content, mono
   metadata. No fill and no radius, so it reads as commentary beside the
   data rather than another object competing with it.

   Every type rule from here through the research note is anchored to
   [data-testid="stAppViewContainer"]. Streamlit's markdown stylesheet
   forces its own font-size onto every p/ol/ul/dl and h1-h4 it renders,
   from a container-class selector at specificity 0,1,1 — which beats a
   lone class of ours. Unanchored, every <p> we
   render came out at the inherited 16px and every <h3> at 28px: the rail's
   12px label, 14px claim and 16px body all collapsed to one size, and a
   finding title outgrew the note's own title. The anchor makes these 0,2,0.
   Measured at 375px on streamlit 1.50.0; test_component_type_scale_outranks
   _streamlits_markdown_stylesheet holds it. */
.tl-evidence-rail {{
  border-left: 2px solid var(--tl-rule);
  padding-left: var(--tl-space-3);
  margin: var(--tl-space-4) 0 0 0;
  max-width: 68ch;
}}
[data-testid="stAppViewContainer"] .tl-evidence-label {{
  font-family: var(--tl-font-mono);
  font-size: 12px;
  line-height: 18px;
  font-weight: 500;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--tl-content-secondary);
  margin: 0;
}}
[data-testid="stAppViewContainer"] .tl-evidence-claim {{
  font-size: 14px;
  line-height: 20px;
  color: var(--tl-content-primary);
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
[data-testid="stAppViewContainer"] .tl-evidence-facts dt {{
  font-size: 12px;
  line-height: 18px;
  font-weight: 500;
  color: var(--tl-content-secondary);
  margin: 0;
}}
[data-testid="stAppViewContainer"] .tl-evidence-facts dd {{
  font-family: var(--tl-font-mono);
  font-size: 12px;
  line-height: 18px;
  color: var(--tl-content-primary);
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
  background: var(--tl-content-secondary);
}}
.tl-evidence-confidence.conf-high::before {{ background: var(--tl-success); }}
.tl-evidence-confidence.conf-medium::before {{ background: var(--tl-warning); }}

/* --- numbered research finding --- */
.tl-finding {{
  display: flex;
  gap: var(--tl-space-4);
  padding: var(--tl-space-6) 0;
  border-top: 1px solid var(--tl-line-hairline);
}}
[data-testid="stAppViewContainer"] .tl-finding-number {{
  font-family: var(--tl-font-mono);
  font-size: 14px;
  line-height: 24px;
  font-weight: 500;
  color: var(--tl-content-secondary);
  margin: 0;
  flex: 0 0 2.5rem;
}}
.tl-finding-body {{ min-width: 0; }}
[data-testid="stAppViewContainer"] .tl-finding-title {{
  font-family: var(--tl-font-ui);
  font-size: 17px;
  line-height: 24px;
  font-weight: 700;
  color: var(--tl-content-primary);
  margin: 0;
}}
[data-testid="stAppViewContainer"] .tl-finding-text {{
  font-size: 16px;
  line-height: 25px;
  color: var(--tl-content-primary);
  margin: var(--tl-space-2) 0 0 0;
  max-width: 68ch;
}}

/* --- editorial readout (interpretation beneath a chart) --- */
.tl-readout {{
  padding-top: var(--tl-space-4);
  border-top: 1px solid var(--tl-line-hairline);
  margin-top: var(--tl-space-4);
}}
.tl-readout-title {{
  font-family: var(--tl-font-ui);
  font-size: 17px;
  line-height: 24px;
  font-weight: 700;
  color: var(--tl-content-primary);
  margin: 0;
}}
.tl-readout-body {{
  font-size: 16px;
  line-height: 25px;
  color: var(--tl-content-primary);
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
  border: 1px solid var(--tl-line-hairline);
  border-radius: var(--tl-radius-full);
  background: var(--tl-surface-elevated);
  font-size: 12px;
  line-height: 18px;
}}
.tl-filter-key {{
  color: var(--tl-content-secondary);
  font-weight: 500;
}}
.tl-filter-value {{
  font-family: var(--tl-font-mono);
  color: var(--tl-content-primary);
}}
.tl-filter-empty {{
  font-size: 12px;
  line-height: 18px;
  color: var(--tl-content-secondary);
}}

/* --- surfaces: white sheet, dark instrument stage, dark reading sheet --- */
.tl-sheet {{
  background: var(--tl-surface-panel);
  border: 1px solid var(--tl-line-hairline);
  border-radius: var(--tl-radius-md);
  padding: var(--tl-space-6);
}}
.tl-chart-stage {{
  background: var(--tl-surface-chart);
  border-radius: var(--tl-radius-md);
  padding: var(--tl-space-4);
  color: var(--tl-content-primary);
}}
.tl-ink-sheet {{
  background: var(--tl-surface-chart);
  border-radius: var(--tl-radius-md);
  padding: var(--tl-space-6);
  color: var(--tl-content-primary);
}}
.tl-ink-sheet .tl-finding-title,
.tl-ink-sheet .tl-finding-text,
.tl-ink-sheet .tl-evidence-claim,
.tl-ink-sheet .tl-readout-title,
.tl-ink-sheet .tl-readout-body {{ color: var(--tl-content-primary); }}
.tl-ink-sheet .tl-evidence-label,
.tl-ink-sheet .tl-finding-number,
.tl-ink-sheet .tl-evidence-facts dt {{ color: var(--tl-content-secondary); }}
.tl-ink-sheet .tl-evidence-facts dd {{ color: var(--tl-content-primary); }}
.tl-ink-sheet .tl-evidence-rail {{ border-left-color: var(--tl-line-hairline); }}
.tl-ink-sheet .tl-finding,
.tl-ink-sheet .tl-readout {{ border-top-color: var(--tl-line-hairline); }}
.tl-ink-sheet .tl-evidence-confidence.conf-high::before {{
  background: var(--tl-success);
}}
.tl-ink-sheet .tl-evidence-confidence.conf-medium::before {{
  background: var(--tl-warning);
}}

/* === KPI CARD (legacy single-card form; superseded by .tl-kpi-strip) === */
.tl-kpi-card {{
  background: var(--tl-surface-panel);
  border: 1px solid var(--tl-line-hairline);
  border-radius: var(--tl-radius-md);
  padding: var(--tl-space-4);
}}
.tl-kpi-label {{
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--tl-content-secondary);
}}
.tl-kpi-value {{
  font-size: 26px;
  font-weight: 500;
  font-family: var(--tl-font-mono);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
  white-space: nowrap;
  color: var(--tl-content-primary);
  line-height: 1.1;
  margin-top: 4px;
}}
.tl-kpi-value.positive {{ color: var(--tl-success); }}
.tl-kpi-value.negative {{ color: var(--tl-danger); }}
.tl-kpi-value.missing {{ color: var(--tl-content-secondary); }}
.tl-kpi-delta {{
  font-size: 12px;
  font-family: var(--tl-font-mono);
  margin-top: 2px;
  color: var(--tl-content-secondary);
}}
.tl-kpi-delta.positive {{ color: var(--tl-success); }}
.tl-kpi-delta.negative {{ color: var(--tl-danger); }}

/* === INSIGHT CARD ===
   Variants use tinted backgrounds + accent icon (NO colored side
   borders — PRODUCT.md anti-pattern; owner decision 2026-07-06). */
.tl-insight-card {{
  background: var(--tl-surface-panel);
  border: 1px solid var(--tl-line-hairline);
  border-radius: var(--tl-radius-md);
  padding: var(--tl-space-4);
}}
.tl-insight-card.strength {{ background: var(--tl-success-dim); }}
.tl-insight-card.leak {{ background: var(--tl-danger-dim); }}
.tl-insight-card.neutral {{ background: var(--tl-surface-elevated); }}
.tl-insight-head {{
  display: flex;
  align-items: center;
  gap: var(--tl-space-2);
  margin-bottom: var(--tl-space-2);
}}
.tl-insight-icon {{ font-size: 16px; }}
.tl-insight-card.strength .tl-insight-icon {{ color: var(--tl-success); }}
.tl-insight-card.leak .tl-insight-icon {{ color: var(--tl-danger); }}
.tl-insight-card.neutral .tl-insight-icon {{ color: var(--tl-content-secondary); }}
.tl-insight-title {{
  font-size: 14px;
  font-weight: 500;
  color: var(--tl-content-primary);
  flex: 1;
}}
.tl-insight-body {{
  font-size: 14px;
  line-height: 20px;
  color: var(--tl-content-primary);
  margin: 0 0 var(--tl-space-2) 0;
}}
.tl-insight-evidence {{
  font-size: 12px;
  color: var(--tl-content-secondary);
  margin: 0;
}}

/* === AI CARD ===
   Neutral border, not a teal outline: a passive container that happens to
   hold generated text is not an action (spec 8). */
.tl-ai-card {{
  background: var(--tl-surface-panel);
  border: 1px solid var(--tl-line-hairline);
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
  color: var(--tl-content-secondary);
}}

/* === FORM SECTION CARD === */
.tl-form-card {{
  background: var(--tl-surface-panel);
  border: 1px solid var(--tl-line-hairline);
  border-radius: var(--tl-radius-md);
  padding: var(--tl-space-6);
  margin-bottom: var(--tl-space-4);
}}
.tl-form-card h3 {{
  font-size: 14px;
  font-weight: 500;
  color: var(--tl-content-primary);
  margin-bottom: var(--tl-space-4);
}}

/* === EMPTY STATE CARD === */
.tl-empty-card {{
  background: var(--tl-surface-panel);
  border: 1px dashed var(--tl-line-hairline);
  border-radius: var(--tl-radius-md);
  padding: var(--tl-space-8);
  text-align: center;
}}
.tl-empty-card .icon {{
  font-family: 'Material Symbols Rounded';
  font-weight: 300;
  line-height: 1;
  font-size: 32px;
  margin-bottom: var(--tl-space-3);
  opacity: 0.4;
}}
.tl-empty-card h4 {{
  font-size: 14px;
  font-weight: 500;
  color: var(--tl-content-primary);
  margin-bottom: var(--tl-space-2);
}}
.tl-empty-card p {{
  font-size: 14px;
  line-height: 20px;
  color: var(--tl-content-secondary);
  max-width: 46ch;
  margin: 0 auto;
}}
/* Onboarding next step. Quiet by design: it sits above the dashboard a
   new trader is trying to read, so it uses the standard surface with a
   neutral hairline. The mono step count carries the only accent — a
   colored side border is a documented anti-pattern here. */
.tl-next-step {{
  border: 1px solid var(--tl-line-hairline);
  border-radius: var(--tl-radius-md);
  background: var(--tl-surface-panel);
  padding: var(--tl-space-4) var(--tl-space-5);
  margin-bottom: var(--tl-space-4);
}}
.tl-next-step-count {{
  font-family: var(--tl-font-mono);
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--tl-accent-action);
}}
.tl-next-step-label {{
  font-size: 17px;
  line-height: 24px;
  font-weight: 700;
  color: var(--tl-content-primary);
  margin-top: var(--tl-space-1);
}}
.tl-next-step-detail {{
  font-size: 14px;
  line-height: 20px;
  color: var(--tl-content-secondary);
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
  color: var(--tl-accent-action);
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
  color: var(--tl-content-primary);
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
  background: var(--tl-content-secondary);
}}
.tl-badge-success {{ background: var(--tl-success-dim); }}
.tl-badge-success::before {{ background: var(--tl-success); }}
.tl-badge-danger {{ background: var(--tl-danger-dim); }}
.tl-badge-danger::before {{ background: var(--tl-danger); }}
.tl-badge-warning {{ background: var(--tl-warning-dim); }}
.tl-badge-warning::before {{ background: var(--tl-warning); }}
.tl-badge-primary {{ background: var(--tl-primary-dim); }}
.tl-badge-primary::before {{ background: var(--tl-accent-action); }}
/* Neutral chips carry setup and tag names — a grey dot on every tag is
   noise, so the neutral variant stays unmarked. */
.tl-badge-neutral {{
  background: var(--tl-surface-elevated);
  color: var(--tl-content-secondary);
}}
.tl-confidence-high {{ background: var(--tl-success-dim); }}
.tl-confidence-high::before {{ background: var(--tl-success); }}
.tl-confidence-medium {{ background: var(--tl-warning-dim); }}
.tl-confidence-medium::before {{ background: var(--tl-warning); }}
.tl-confidence-low {{
  background: var(--tl-surface-elevated);
  color: var(--tl-content-secondary);
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
  background: var(--tl-accent-action);
  margin-bottom: var(--tl-space-2);
}}
[data-testid="stAppViewContainer"] .tl-section-title {{
  margin: 0;
  font-family: var(--tl-font-display);
  font-size: 36px;
  line-height: 42px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--tl-content-primary);
}}
[data-testid="stAppViewContainer"] .tl-section-subtitle {{
  font-size: 14px;
  line-height: 20px;
  color: var(--tl-content-secondary);
  margin-top: 2px;
}}
/* Chart card title (analytics) — one quiet weight below section titles. */
.tl-chart-title {{
  font-size: 14px;
  font-weight: 500;
  letter-spacing: 0.01em;
  color: var(--tl-content-primary);
  margin: 0 0 var(--tl-space-2) 0;
}}
.tl-chart-stage .tl-chart-title {{ color: var(--tl-content-primary); }}

/* === ERROR BOX (components/ui.error_box) ===
   Red is reserved for errors, so this is one of the few places the danger
   hue is load-bearing. Same rule as the banners: ink copy on the danger
   wash with the hue as a border and mark, never as the text colour. */
.tl-error-box {{
  border: 1px solid var(--tl-danger);
  border-radius: var(--tl-radius-sm);
  background: var(--tl-danger-dim);
  padding: var(--tl-space-3) var(--tl-space-4);
  color: var(--tl-content-primary);
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
  background: var(--tl-danger);
}}

/* === BANNERS ===
   Same rule as badges: ink copy on a quiet ground, hue carried by a mark. */
.tl-banner {{
  border-radius: var(--tl-radius-sm);
  border: 1px solid var(--tl-line-hairline);
  padding: var(--tl-space-3) var(--tl-space-4);
  font-size: 14px;
  line-height: 20px;
  color: var(--tl-content-primary);
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
  background: var(--tl-content-secondary);
}}
.tl-banner-warning {{ background: var(--tl-warning-dim); }}
.tl-banner-warning::before {{ background: var(--tl-warning); }}
.tl-banner-info {{ background: var(--tl-primary-dim); }}
.tl-banner-info::before {{ background: var(--tl-accent-action); }}
.tl-banner-danger {{ background: var(--tl-danger-dim); }}
.tl-banner-danger::before {{ background: var(--tl-danger); }}

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
/* Done recedes. Filling completed steps with the action colour put five
   identical bright pills and four teal connectors on step 5, beside a teal
   Continue button — teal is action and focus (4.1), and a step the trader
   has already left is neither. A finished step is marked by its glyph and
   its drawn edge, so exactly one circle on the rail carries the accent and
   it is always the one the trader is standing on. */
.tl-step-circle.done {{
  background: var(--tl-surface-elevated);
  color: var(--tl-content-secondary);
  border: 1px solid var(--tl-line-strong);
}}
.tl-step-circle.active {{
  background: var(--tl-accent-action);
  color: var(--tl-surface-panel);
  box-shadow: 0 0 0 3px var(--tl-primary-dim);
}}
/* Future differs from done by glyph and edge, not by tone: done carries the
   check behind a strong line, future carries its number with no edge. */
.tl-step-circle.future {{
  background: var(--tl-surface-elevated);
  color: var(--tl-content-secondary);
}}
.tl-step-label {{
  font-size: 12px;
  line-height: 18px;
  color: var(--tl-content-secondary);
  margin-top: 4px;
}}
.tl-step-connector {{
  flex: 1;
  height: 2px;
  margin-bottom: 16px;
}}
/* Travelled ground is drawn, not accented — the strong line is the token for
   a boundary that carries meaning (4.4), and it stays legible against the
   hairline the untravelled segments use. */
.tl-step-connector.done {{ background: var(--tl-line-strong); }}
.tl-step-connector.future {{ background: var(--tl-line-hairline); }}

/* === AI REVIEWS — the research note ===
   The note body is a focused DARK reading surface inside the light
   workspace (spec 7): filters and controls stay on the workspace, the
   thing being read gets its own plane. */
.tl-note {{
  background: var(--tl-surface-chart);
  border-radius: var(--tl-radius-md);
  padding: var(--tl-space-6);
  color: var(--tl-content-primary);
  max-width: 72ch;
}}
.tl-note-head {{
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--tl-space-4);
  flex-wrap: wrap;
  padding-bottom: var(--tl-space-3);
  border-bottom: 1px solid var(--tl-line-hairline);
}}
/* Two classes, not one: the global heading rule is
   `[data-testid="stAppViewContainer"] h2` (specificity 0,1,1), which beats
   a lone class and painted these near-black on the dark sheet. */
[data-testid="stAppViewContainer"] .tl-note .tl-note-title,
[data-testid="stAppViewContainer"] .st-key-tl_note_sheet .tl-note-title {{
  font-family: var(--tl-font-display);
  font-size: 22px;
  line-height: 28px;
  font-weight: 700;
  color: var(--tl-content-primary);
  margin: 0;
}}
[data-testid="stAppViewContainer"] .tl-note-sample {{
  font-family: var(--tl-font-mono);
  font-size: 12px;
  line-height: 18px;
  color: var(--tl-content-secondary);
  margin: 0;
}}
/* The thesis is the one sentence a reader must not miss, so it is the
   largest text on the surface — one step above the findings that support
   it, not a heading competing with the title. */
[data-testid="stAppViewContainer"] .tl-note-thesis {{
  font-size: 19px;
  line-height: 28px;
  color: var(--tl-content-primary);
  margin: var(--tl-space-4) 0 0 0;
}}
/* --- dark-surface repaint for the shared components ---
   The Evidence Rail and the numbered finding are built once and used on
   BOTH reading surfaces, so a rule that names only one leaves the other
   unstyled. Every rule below must therefore name BOTH: `.tl-note` (the
   note we compose ourselves) and `.st-key-tl_note_sheet` (the container
   the generated note is written into). Listing only `.tl-note` left the
   rail's claim and values at 1.07:1 on the generated note — invisible, and
   caught only in the browser. test_dark_surface_overrides_name_both_reading_surfaces
   holds the pair together. */
[data-testid="stAppViewContainer"] .tl-note .tl-finding,
[data-testid="stAppViewContainer"] .st-key-tl_note_sheet .tl-finding {{ border-top-color: var(--tl-line-hairline); }}
[data-testid="stAppViewContainer"] .tl-note .tl-finding-title,
[data-testid="stAppViewContainer"] .tl-note .tl-finding-text,
[data-testid="stAppViewContainer"] .tl-note .tl-evidence-claim,
[data-testid="stAppViewContainer"] .st-key-tl_note_sheet .tl-finding-title,
[data-testid="stAppViewContainer"] .st-key-tl_note_sheet .tl-finding-text,
[data-testid="stAppViewContainer"] .st-key-tl_note_sheet .tl-evidence-claim {{ color: var(--tl-content-primary); }}
[data-testid="stAppViewContainer"] .tl-note .tl-finding-number,
[data-testid="stAppViewContainer"] .tl-note .tl-evidence-label,
[data-testid="stAppViewContainer"] .tl-note .tl-evidence-facts dt,
[data-testid="stAppViewContainer"] .st-key-tl_note_sheet .tl-finding-number,
[data-testid="stAppViewContainer"] .st-key-tl_note_sheet .tl-evidence-label,
[data-testid="stAppViewContainer"] .st-key-tl_note_sheet .tl-evidence-facts dt {{ color: var(--tl-content-secondary); }}
[data-testid="stAppViewContainer"] .tl-note .tl-evidence-facts dd,
[data-testid="stAppViewContainer"] .st-key-tl_note_sheet .tl-evidence-facts dd {{ color: var(--tl-content-primary); }}
[data-testid="stAppViewContainer"] .tl-note .tl-evidence-rail,
[data-testid="stAppViewContainer"] .st-key-tl_note_sheet .tl-evidence-rail {{ border-left-color: var(--tl-line-hairline); }}
/* The confidence dot is a mark, so it needs the 3:1 non-text floor against
   the stage — the workspace's muted grey does not clear it. */
[data-testid="stAppViewContainer"] .tl-note .tl-evidence-confidence::before,
[data-testid="stAppViewContainer"] .st-key-tl_note_sheet .tl-evidence-confidence::before {{
  background: var(--tl-content-secondary);
}}
[data-testid="stAppViewContainer"] .tl-note .tl-evidence-confidence.conf-high::before,
[data-testid="stAppViewContainer"] .st-key-tl_note_sheet .tl-evidence-confidence.conf-high::before {{
  background: var(--tl-success);
}}
[data-testid="stAppViewContainer"] .tl-note .tl-evidence-confidence.conf-medium::before,
[data-testid="stAppViewContainer"] .st-key-tl_note_sheet .tl-evidence-confidence.conf-medium::before {{
  background: var(--tl-warning);
}}
.tl-note-actions {{
  margin-top: var(--tl-space-6);
  padding-top: var(--tl-space-4);
  border-top: 1px solid var(--tl-line-hairline);
}}
[data-testid="stAppViewContainer"] .tl-note .tl-note-actions-title,
[data-testid="stAppViewContainer"] .st-key-tl_note_sheet .tl-note-actions-title {{
  font-family: var(--tl-font-ui);
  font-size: 14px;
  font-weight: 500;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--tl-content-secondary);
  margin: 0 0 var(--tl-space-2) 0;
}}
.tl-note-actions ul {{
  margin: 0;
  padding-left: var(--tl-space-4);
}}
[data-testid="stAppViewContainer"] .tl-note-actions li {{
  font-size: 16px;
  line-height: 25px;
  color: var(--tl-content-primary);
  margin-bottom: var(--tl-space-1);
}}
[data-testid="stAppViewContainer"] .tl-note-limitation {{
  font-size: 14px;
  line-height: 20px;
  color: var(--tl-content-secondary);
  margin: var(--tl-space-4) 0 0 0;
}}
/* Supporting detail, collapsed. A native <details> needs no script and is
   keyboard-reachable by default. */
.tl-note-evidence {{
  margin-top: var(--tl-space-4);
  border-top: 1px solid var(--tl-line-hairline);
  padding-top: var(--tl-space-3);
}}
[data-testid="stAppViewContainer"] .tl-note-evidence summary {{
  font-size: 14px;
  color: var(--tl-content-secondary);
  cursor: pointer;
  min-height: 44px;
  display: flex;
  align-items: center;
}}
.tl-note-evidence summary:focus-visible {{
  outline: 2px solid var(--tl-focus);
  outline-offset: 2px;
}}
[data-testid="stAppViewContainer"] .tl-note-evidence ul {{
  margin: 0;
  padding-left: var(--tl-space-4);
  font-size: 14px;
  line-height: 22px;
  color: var(--tl-content-secondary);
}}
[data-testid="stAppViewContainer"] .tl-note-generated {{
  font-family: var(--tl-font-mono);
  font-size: 12px;
  color: var(--tl-content-secondary);
  margin: var(--tl-space-4) 0 0 0;
}}

/* Skeleton: the note's own geometry while generation runs, so the page
   does not jump when the note lands. */
.tl-note-skeleton .tl-skeleton-line {{
  height: 16px;
  border-radius: 4px;
  background: var(--tl-surface-elevated);
  margin-bottom: var(--tl-space-3);
}}
.tl-skeleton-line.w90 {{ width: 90%; }}
.tl-skeleton-line.w80 {{ width: 80%; }}
.tl-skeleton-line.w70 {{ width: 70%; }}
.tl-skeleton-line.w60 {{ width: 60%; }}
@media (prefers-reduced-motion: no-preference) {{
  .tl-note-skeleton .tl-skeleton-line {{
    animation: tl-skeleton-pulse 1.4s ease-in-out infinite;
  }}
  @keyframes tl-skeleton-pulse {{
    0%, 100% {{ opacity: 1; }}
    50% {{ opacity: 0.55; }}
  }}
}}

/* Generated prose keeps the dark surface too. The model's markdown is
   rendered by Streamlit, so it arrives as ordinary elements that need
   colouring rather than our own classed markup. */
/* The plane hugs the reading measure. Stretched to the full column it is
   a dark slab with prose down one edge — the surface should be the shape
   of the thing being read. */
.st-key-tl_note_sheet {{
  background: var(--tl-surface-chart);
  border-radius: var(--tl-radius-md);
  padding: var(--tl-space-6);
  max-width: 78ch;
}}
.st-key-tl_note_sheet [data-testid="stMarkdownContainer"] {{
  color: var(--tl-content-primary);
  max-width: 72ch;
}}
.st-key-tl_note_sheet [data-testid="stMarkdownContainer"] h1,
.st-key-tl_note_sheet [data-testid="stMarkdownContainer"] h2,
.st-key-tl_note_sheet [data-testid="stMarkdownContainer"] h3,
.st-key-tl_note_sheet [data-testid="stMarkdownContainer"] h4,
.st-key-tl_note_sheet [data-testid="stMarkdownContainer"] strong {{
  color: var(--tl-content-primary);
}}

/* === STRATEGY PROFILE — the playbook summary ===
   A compact functional header, not a hero. The page it introduces is a
   long form, so this states three things and stops: whose playbook, how
   complete, and what reads it. The photographic banner it replaces put a
   75%-dimmed image behind that information.

   Type rules here carry the app-container anchor for the reason given at
   the Evidence Rail: Streamlit sizes every p and h1-h4 it renders from a
   0,1,1 selector, which beats a lone class of ours. */
.tl-playbook {{
  background: var(--tl-surface-panel);
  border: 1px solid var(--tl-line-hairline);
  border-radius: var(--tl-radius-md);
  padding: var(--tl-space-5) var(--tl-space-6);
  margin-bottom: var(--tl-space-4);
}}
.tl-playbook-head {{
  display: flex;
  align-items: baseline;
  gap: var(--tl-space-3);
  flex-wrap: wrap;
}}
[data-testid="stAppViewContainer"] .tl-playbook-name {{
  font-family: var(--tl-font-display);
  font-size: 20px;
  line-height: 28px;
  font-weight: 700;
  color: var(--tl-content-primary);
  margin: 0;
}}
[data-testid="stAppViewContainer"] .tl-playbook-meta {{
  font-family: var(--tl-font-mono);
  font-size: 12px;
  line-height: 18px;
  color: var(--tl-content-secondary);
  margin: 0 0 0 auto;
}}
/* Completion. The figure is the message; the rule underneath is a second
   reading of the same number, so it is aria-hidden rather than announced
   twice. */
.tl-playbook-progress {{
  display: block;
  height: 3px;
  border-radius: var(--tl-radius-full);
  background: var(--tl-line-hairline);
  margin: var(--tl-space-3) 0 var(--tl-space-2) 0;
  overflow: hidden;
}}
.tl-playbook-progress span {{
  display: block;
  height: 100%;
  background: var(--tl-accent-action);
}}
[data-testid="stAppViewContainer"] .tl-playbook-count {{
  font-family: var(--tl-font-mono);
  font-size: 12px;
  line-height: 18px;
  letter-spacing: 0.04em;
  color: var(--tl-content-secondary);
  margin: 0;
}}
[data-testid="stAppViewContainer"] .tl-playbook-why {{
  font-size: 14px;
  line-height: 21px;
  color: var(--tl-content-secondary);
  margin: var(--tl-space-2) 0 0 0;
  max-width: 68ch;
}}
/* Saved values, read-only. Grouped under their own label so a chip row is
   never mistaken for the field that edits it. */
.tl-playbook-facets {{
  display: flex;
  flex-direction: column;
  gap: var(--tl-space-2);
  margin-top: var(--tl-space-4);
  padding-top: var(--tl-space-3);
  border-top: 1px solid var(--tl-line-hairline);
}}
.tl-playbook-facet {{
  display: flex;
  align-items: baseline;
  gap: var(--tl-space-3);
  flex-wrap: wrap;
}}
[data-testid="stAppViewContainer"] .tl-playbook-facet-label {{
  font-family: var(--tl-font-mono);
  font-size: 11px;
  line-height: 18px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--tl-content-secondary);
  margin: 0;
  flex: 0 0 5.5rem;
}}
.tl-playbook-facet .tl-chip-row {{ margin: 0; }}

/* Opening a rule section is the one state change on this page worth
   conveying: without it the panel's contents appear out of nothing, which
   reads as a glitch rather than a disclosure. Opacity and a 4px lift only,
   at 180ms on the project's ease-out — the same reveal as the Journal's
   trade detail and the wizard's step, so the product has one rhythm rather
   than a third.

   Scoped to the playbook form, not to [data-testid="stExpander"]: every
   st.expander in the app carries that testid, so an unscoped rule would
   animate the Journal's filters, the wizard's screenshot panel, Settings
   and the auth screen — motion on five pages that asked for none.

   Nothing else on this page moves. Save is a form submit a trader repeats
   all session, and validation text has to be readable the instant it
   exists — animating either would make the interface feel slower at the
   two moments the user is watching most closely. */
.st-key-tl_playbook_form [data-testid="stExpander"] details[open] > summary + div {{
  animation: tl-section-in 180ms var(--tl-ease-out) both;
}}
@keyframes tl-section-in {{
  from {{ opacity: 0; transform: translateY(4px); }}
  to {{ opacity: 1; transform: none; }}
}}

/* Field-level validation. Sits under the input it is about, stays until
   the value is fixed, and announces itself — a toast did none of the
   three. Red is reserved for errors, which this is. */
[data-testid="stAppViewContainer"] .tl-field-error {{
  font-size: 13px;
  line-height: 20px;
  font-weight: 500;
  color: var(--tl-danger);
  margin: var(--tl-space-1) 0 0 0;
}}

/* === SETTINGS — deliberately the quietest page ===
   Nothing here is the product. No card, no chart, no promotion: labelled
   rows on the workspace, one rule between sections instead of six
   dividers, and the only bordered object on the page reserved for the two
   actions that destroy data. */
.tl-settings-row {{
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--tl-space-4);
  flex-wrap: wrap;
  padding: var(--tl-space-3) 0;
  border-bottom: 1px solid var(--tl-line-hairline);
}}
[data-testid="stAppViewContainer"] .tl-settings-label {{
  font-size: 14px;
  line-height: 21px;
  font-weight: 500;
  color: var(--tl-content-primary);
  margin: 0;
}}
[data-testid="stAppViewContainer"] .tl-settings-value {{
  font-family: var(--tl-font-mono);
  font-size: 13px;
  line-height: 21px;
  color: var(--tl-content-secondary);
  margin: 0;
  text-align: right;
  overflow-wrap: anywhere;
}}
[data-testid="stAppViewContainer"] .tl-settings-note {{
  font-size: 13px;
  line-height: 20px;
  color: var(--tl-content-secondary);
  margin: var(--tl-space-2) 0 0 0;
  max-width: 68ch;
}}

/* Save feedback, beside the control that changed. Settings are saved one
   at a time, so a toast in the corner is both too far away and gone before
   the eye gets there. The status is a live region: it appears after an
   action the user took, and a screen reader has to hear it. */
[data-testid="stAppViewContainer"] .tl-setting-status {{
  font-size: 13px;
  line-height: 20px;
  font-weight: 500;
  margin: var(--tl-space-2) 0 0 0;
}}
.tl-setting-status::before {{
  content: '';
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-right: 8px;
  border-radius: var(--tl-radius-full);
  vertical-align: middle;
}}
/* Ink on the quiet ground, hue only in the dot — the wash-as-text-
   background pattern fails AA at every tint strength (measured, Task 1). */
[data-testid="stAppViewContainer"] .tl-setting-status.ok {{
  color: var(--tl-content-primary);
}}
.tl-setting-status.ok::before {{ background: var(--tl-success); }}
[data-testid="stAppViewContainer"] .tl-setting-status.fail {{
  color: var(--tl-danger);
}}
.tl-setting-status.fail::before {{ background: var(--tl-danger); }}

/* Integration state. Not an error when it is unset — an optional key that
   has not been supplied is a state with an action attached, so it gets the
   neutral dot and a sentence, not a red panel. */
[data-testid="stAppViewContainer"] .tl-settings-state {{
  font-size: 14px;
  line-height: 21px;
  color: var(--tl-content-primary);
  margin: 0;
}}
.tl-settings-state::before {{
  content: '';
  display: inline-block;
  width: 8px;
  height: 8px;
  margin-right: 10px;
  border-radius: var(--tl-radius-full);
  background: var(--tl-content-secondary);
  vertical-align: middle;
}}
.tl-settings-state.on::before {{ background: var(--tl-success); }}

/* The one bordered object on the page. A full border, not a red side
   stripe: the section is dangerous, so it is enclosed rather than
   decorated, and the hue stays on the heading and the buttons. */
/* The border goes on the KEYED CONTAINER, not on the heading markup: the
   expanders, their confirmation fields and their buttons are Streamlit
   elements rendered as siblings of that markup, so a border drawn around
   the heading alone would enclose a title and leave both destructive
   actions outside the box it is supposed to be warning about. */
.st-key-tl_danger_zone {{
  border: 1px solid var(--tl-danger);
  border-radius: var(--tl-radius-md);
  padding: var(--tl-space-5) var(--tl-space-6);
  margin-top: var(--tl-space-12);
}}
.tl-danger-zone {{
  margin-bottom: var(--tl-space-4);
}}
[data-testid="stAppViewContainer"] .tl-danger-zone-title {{
  font-family: var(--tl-font-ui);
  font-size: 15px;
  line-height: 22px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--tl-danger);
  margin: 0;
}}
[data-testid="stAppViewContainer"] .tl-danger-zone-lede {{
  font-size: 14px;
  line-height: 21px;
  color: var(--tl-content-secondary);
  margin: var(--tl-space-2) 0 0 0;
  max-width: 68ch;
}}
/* Every control inside the zone is destructive, so the confirm buttons
   carry the danger hue rather than the brand teal — which everywhere else
   in the product means "the useful thing to do next". */
.st-key-tl_danger_zone .stButton button {{
  border-color: var(--tl-danger);
  color: var(--tl-danger);
}}
.st-key-tl_danger_zone .stButton button:disabled {{
  border-color: var(--tl-line-hairline);
  color: var(--tl-content-secondary);
}}

/* === JOURNAL === */
/* The result count, beside the view selector. Mono so the figure lines up
   with the ledger's own numerals, and right-aligned so it reads as a
   caption on the selector rather than a heading of its own. */
.tl-journal-count {{
  font-family: var(--tl-font-mono);
  font-size: 12px;
  line-height: 18px;
  color: var(--tl-content-secondary);
  text-align: right;
  margin: 0;
}}
/* Opening a trade is a real change of context, so the detail gets one brief
   reveal — the ONLY animation on this page. Rows, sorting, filtering and
   hover stay instant: those happen dozens of times a session, and motion
   there reads as lag rather than feedback. */
.st-key-tl_trade_detail {{
  animation: tl-detail-in 180ms var(--tl-ease-out) both;
}}
@keyframes tl-detail-in {{
  from {{ opacity: 0; transform: translateY(4px); }}
  to {{ opacity: 1; transform: none; }}
}}

/* A calendar day is a button a thumb has to hit, so it carries the same
   44px floor as every other control — at every width, not just on a phone.
   Descendant combinator, not `>`: these buttons pass `help=`, which wraps
   them in a tooltip div, so `.stButton > button` never matches them.
   Keyed on the calendar form so every page mounting it inherits one rule. */
.st-key-tl_full_calendar [data-testid="stColumn"] .stButton button {{
  min-height: 44px;
}}

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

/* Screenshot analysis, waiting. This block stands exactly where the two-panel
   detection review will land, so it reserves that height instead of
   collapsing to a spinner line and letting the results shove the page down
   when they arrive (spec 6.2, "no collapse-and-jump"). The height is the
   reservation; nothing here moves, so there is no reduced-motion case. */
.st-key-tl_analysis_pending {{
  min-height: 320px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: var(--tl-space-3);
  padding: var(--tl-space-5);
  background: var(--tl-surface-panel);
  border: 1px solid var(--tl-line-hairline);
  border-radius: var(--tl-radius-md);
  color: var(--tl-content-secondary);
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
  z-index: var(--tl-z-raised);
  background: var(--tl-surface-canvas);
  border-top: 1px solid var(--tl-line-hairline);
  padding: var(--tl-space-3) 0 var(--tl-space-2) 0;
  margin-top: var(--tl-space-6);
}}
.tl-wizard-draft {{
  font-family: var(--tl-font-mono);
  font-size: 12px;
  line-height: 18px;
  color: var(--tl-content-secondary);
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
  background: var(--tl-surface-panel);
  border: 1px solid var(--tl-line-hairline);
  border-radius: var(--tl-radius-md);
  padding: var(--tl-space-4);
  cursor: pointer;
  transition: border-color var(--tl-dur-state) var(--tl-ease-out);
}}
@media (hover: hover) and (pointer: fine) {{
  .tl-action-card:hover {{
    border-color: var(--tl-accent-action);
  }}
}}
.tl-action-card:focus-within {{
  border-color: var(--tl-accent-action);
  box-shadow: var(--tl-shadow);
}}

/* === HERO KPI ROW (dashboard) ===
   Superseded by .tl-kpi-strip; kept legible until Overview is recomposed.
   The background image the old hero carried is not reinstated —
   decoration behind figures is what made that dashboard hard to read. */
.tl-hero-wrap {{
  border: 1px solid var(--tl-line-hairline);
  border-radius: var(--tl-radius-md);
  padding: var(--tl-space-6);
  margin-bottom: var(--tl-space-4);
  background-color: var(--tl-surface-panel);
}}
.tl-kpi-row {{
  display: flex;
  gap: var(--tl-space-3);
  flex-wrap: wrap;
}}
.tl-kpi-row .tl-kpi-card {{
  flex: 1 1 150px;
  min-width: 150px;
  background: var(--tl-surface-panel);
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
  color: var(--tl-content-secondary);
  padding: var(--tl-space-2) var(--tl-space-3);
  border-bottom: 1px solid var(--tl-line-hairline);
}}
.tl-table td {{
  padding: var(--tl-space-3);
  border-bottom: 1px solid var(--tl-line-hairline);
  color: var(--tl-content-primary);
  transition: background var(--tl-dur-state) var(--tl-ease-out);
}}
.tl-table td.mono {{
  font-family: var(--tl-font-mono);
  font-variant-numeric: tabular-nums;
}}
.tl-table th.num, .tl-table td.num {{ text-align: right; }}
.tl-table td.pnl-pos {{ color: var(--tl-success); }}
.tl-table td.pnl-neg {{ color: var(--tl-danger); }}
/* Gated: on a touch device :hover latches after a tap, leaving a row
   tinted as though it were selected. */
@media (hover: hover) and (pointer: fine) {{
  .tl-table tr:hover td {{ background: var(--tl-surface-elevated); }}
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
  color: var(--tl-content-primary);
  margin: 0 0 var(--tl-space-2) 0;
}}
.tl-welcome-sub {{
  font-size: 16px;
  line-height: 25px;
  color: var(--tl-content-secondary);
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
  color: var(--tl-content-primary);
  margin-bottom: 2px;
}}
.tl-action-sub {{
  display: block;
  font-size: 12px;
  color: var(--tl-content-secondary);
  margin-bottom: var(--tl-space-2);
}}
.tl-action-go {{
  display: block;
  font-size: 14px;
  font-weight: 500;
  color: var(--tl-accent-action);
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
  color: var(--tl-content-primary);
  background: var(--tl-surface-elevated);
  border-radius: 4px;
}}

/* === FOCUS ===
   One visible ring everywhere, on both surface families. Focus is never
   removed; keyboard users navigate the whole product. */
[data-testid="stAppViewContainer"] :focus-visible {{
  outline: 2px solid var(--tl-accent-action);
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
  background: var(--tl-content-secondary);
}}
[class*="st-key-calday_"][class*="_positive"] button::before {{
  background: var(--tl-success);
}}
[class*="st-key-calday_"][class*="_negative"] button::before {{
  background: var(--tl-danger);
}}
.tl-cal-legend {{
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--tl-space-4);
  font-size: 12px;
  color: var(--tl-content-secondary);
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
  background: var(--tl-content-secondary);
  display: inline-block;
}}
.tl-cal-dot.positive {{ background: var(--tl-success); }}
.tl-cal-dot.negative {{ background: var(--tl-danger); }}

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
  [class*="st-key-tl_step_"],
  .st-key-tl_trade_detail,
  .st-key-tl_playbook_form
    [data-testid="stExpander"] details[open] > summary + div {{
    animation: none;
  }}
}}

/* === TOUCH TARGETS ON STREAMLIT'S OWN CONTROLS ===
   Our components carry the 44px floor themselves. Streamlit's defaults do
   not. Measured on 1.50.0: lens options 26px, date field 38px, sidebar
   handle 28px, in-content page link 32px, and buttons 40px above the phone
   breakpoint. Every rule here is set at EVERY width — a pointer is not the
   only reason for a comfortable target, and a floor that exists only below
   767px is one that regresses the moment anyone measures at 1440px, which
   is exactly how the button case was found. */

/* Radio options only. `[data-baseweb="radio"]` is on the option labels;
   the widget's own <label> carries the stWidgetLabel testid instead and
   collapses to 0px when label_visibility="collapsed" — matching it would
   inject 44px of empty space above every lens selector. */
[data-testid="stRadio"] label[data-baseweb="radio"] {{
  min-height: 44px;
  align-items: center;
}}
[data-testid="stDateInput"] input {{
  min-height: 44px;
}}
/* Selectboxes. The <input> BaseWeb nests inside is a 22px a11y shim, not
   the target — the control a thumb actually hits is the wrapper div, which
   measured 40px. Settings' timezone picker is the whole of Preferences. */
[data-testid="stSelectbox"] [data-baseweb="select"] > div {{
  min-height: 44px;
}}
/* Text fields. This too lived inside the phone breakpoint, so every input
   on the playbook form was 38px on a desktop and 44px on a phone. */
[data-testid="stTextInput"] input {{
  min-height: 44px;
}}
/* An accordion header is the control that opens a section — on the
   playbook it is the only way to reach five of the six. Streamlit gives it
   4px 12px of padding and nothing else. */
[data-testid="stExpander"] summary {{
  min-height: 44px;
  display: flex;
  align-items: center;
}}
/* The collapse handle carries its testid on the wrapper, the expand handle
   on the button itself — hence the two shapes. */
/* The collapse chevron inherits workspace ink, so on the dark rail it was
   1.05:1 — a control you cannot see is a control you do not have. */
[data-testid="stSidebarCollapseButton"] button,
[data-testid="stSidebarCollapseButton"] button * {{
  color: var(--tl-content-primary);
}}
[data-testid="stSidebarCollapseButton"] button,
[data-testid="stExpandSidebarButton"] {{
  min-width: 44px;
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}}
/* Buttons. Descendant, not `>`: a button that passes `help=` is wrapped in
   a tooltip div, so `.stButton > button` never reaches it. This lived
   inside the phone breakpoint and made the same control 44px on a phone
   and 40px on a desktop — "Regenerate this week", measured at 1440px. */
.stButton button,
.stFormSubmitButton button {{
  min-height: 44px;
}}
/* Download and upload render their own buttons outside .stButton, so the
   rule above never reached them: Settings' export and its CSV browse
   button both measured 40px. */
[data-testid="stDownloadButton"] button,
[data-testid="stFileUploader"] button {{
  min-height: 44px;
}}
/* Page links in the page body. The sidebar's nav links are already 44px
   from the shell pass; an in-content one ("Open these trades in the
   Journal") was 32px. inline-flex gives the hit area without changing how
   the link reads. */
[data-testid="stPageLink-NavLink"] {{
  min-height: 44px;
  display: inline-flex;
  align-items: center;
}}

/* Nav icons. stIconMaterial sets its OWN colour, so the rail's text rule
   never reached it: every icon in the sidebar rendered workspace ink on
   the dark rail at 1.1:1, and on the active item's surface at 1.04:1 —
   six invisible icons. Inheriting the link means the nav icons go light
   and the teal action's icon stays dark, from one rule. */
[data-testid="stSidebar"] [data-testid="stIconMaterial"] {{
  color: inherit;
}}

/* === STREAMLIT'S OWN SECONDARY TEXT ===
   Measured on white: the multiselect placeholder and the file-uploader's
   "Limit 200MB per file" line both land at 4.4:1, and an empty menu's
   "No options to select" at 2.46:1. Close is not passing — these carry the
   workspace's muted token, which IS measured. */
/* The multiselect placeholder is a plain div BaseWeb gives no attribute
   to, painted rgba(ink, 0.6) — 4.4:1 over white. Once values are chosen
   they render as [data-baseweb="tag"] chips instead, so recolouring the
   plain text inside a MULTIselect only ever hits the placeholder. */
/* Streamlit paints its secondary text as rgba(ink, 0.4-0.6), which lands
   at 4.4:1 for a placeholder and 2.46:1 for an empty menu — the alpha is
   not ours to change, so the colour is replaced with the measured muted
   token. Chosen values (tags, the selected option) are restored to ink
   below: a value the trader picked is content, not a hint. */
[data-testid="stMultiSelect"] [data-baseweb="select"] div,
[data-baseweb="popover"] [data-baseweb="menu"] li,
[data-testid="stFileUploader"] small,
[data-testid="stFileUploaderDropzoneInstructions"] span,
[data-baseweb="menu"] li {{
  color: var(--tl-content-secondary);
}}

/* A multiselect shows chosen values as tags, so the plain text inside one
   is only ever the placeholder — but the tags sit inside the same subtree
   and must stay content-coloured. A SELECTBOX always has a value and never
   shows a placeholder at all, which is why it is absent above: muting it
   greyed out the chosen value, measured at 5.61:1 where ink belongs. */
[data-testid="stMultiSelect"] [data-baseweb="tag"],
[data-testid="stMultiSelect"] [data-baseweb="tag"] div,
[data-baseweb="popover"] [data-baseweb="menu"] li[aria-selected="true"] {{
  color: var(--tl-content-primary);
}}

/* A data table must scroll inside its own frame rather than push the page
   sideways; Streamlit leaves overflow-x visible and its grid ran 9px wide. */
[data-testid="stDataFrame"] {{
  overflow-x: auto;
}}

/* === OVERVIEW BAND 2 — the discipline panel ===
   Band 1 above it is a ruled KPI strip. This is deliberately a different
   form: figure above sample, hairline-divided rows on one panel rather than
   four tiles. Five bands, five forms — the anti-grid rule is what stops the
   Overview becoming a wall of equal cards.

   No tone attribute is ever set here. Rule adherence and consistency are
   process measures, and red/green is reserved for money; a discipline figure
   painted green would be claiming an outcome it does not describe. */
.tl-discipline {{
  background: var(--tl-surface-panel);
  border: 1px solid var(--tl-line-hairline);
  border-radius: var(--tl-radius-md);
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
}}
.tl-discipline-row {{
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--tl-space-4) var(--tl-space-5);
  border-right: 1px solid var(--tl-line-hairline);
}}
.tl-discipline-row:last-child {{
  border-right: none;
}}
.tl-discipline-label {{
  font-family: var(--tl-font-ui);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--tl-content-secondary);
}}
/* The figure is always text. Never encoded only in the length or fill of an
   indicator, and never hover-only — spec 5.3's threshold-legibility rule. */
.tl-discipline-value {{
  font-family: var(--tl-font-mono);
  font-size: 22px;
  line-height: 1.2;
  color: var(--tl-content-primary);
  font-variant-numeric: tabular-nums;
}}
.tl-discipline-sample {{
  font-family: var(--tl-font-mono);
  font-size: 11px;
  color: var(--tl-content-secondary);
  font-variant-numeric: tabular-nums;
}}
.tl-discipline-note {{
  margin: var(--tl-space-1) 0 0 0;
  font-size: 12px;
  line-height: 1.45;
  color: var(--tl-content-secondary);
  max-width: 34ch;
}}
@media (max-width: 767px) {{
  .tl-discipline {{
    grid-template-columns: 1fr;
  }}
  .tl-discipline-row {{
    border-right: none;
    border-bottom: 1px solid var(--tl-line-hairline);
  }}
  .tl-discipline-row:last-child {{
    border-bottom: none;
  }}
}}

/* === OVERVIEW BAND 4 — ranked performance lists ===
   A third form again: not a strip, not a panel of figures, but a short
   ordered list where the rank marker only appears when ranking is earned.
   Ranked lists rather than pie charts — a trader comparing session P&L needs
   to read magnitudes, not compare silhouettes.

   The ordinal is drawn from data-rank rather than <ol>'s own numbering, so a
   list that may not be ranked simply carries no marker and CSS never has to
   hide one. */
.tl-ranked {{
  background: var(--tl-surface-panel);
  border: 1px solid var(--tl-line-hairline);
  border-radius: var(--tl-radius-md);
  padding: var(--tl-space-4) var(--tl-space-5);
}}
.tl-ranked-title {{
  margin: 0 0 var(--tl-space-3) 0;
  font-family: var(--tl-font-ui);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--tl-content-secondary);
}}
.tl-ranked-rows {{
  list-style: none;
  margin: 0;
  padding: 0;
  counter-reset: none;
}}
.tl-ranked-row {{
  display: grid;
  grid-template-columns: 1fr auto;
  grid-template-areas: "label value" "sample value";
  gap: 0 var(--tl-space-4);
  padding: var(--tl-space-3) 0;
  border-bottom: 1px solid var(--tl-line-hairline);
}}
.tl-ranked-row:last-child {{
  border-bottom: none;
}}
.tl-ranked-label {{
  grid-area: label;
  color: var(--tl-content-primary);
  font-size: 14px;
}}
/* The leader is marked with a rule, not a medal: this is a ranking of
   evidence, not a scoreboard. */
.tl-ranked-row[data-rank="1"] .tl-ranked-label {{
  font-weight: 600;
}}
.tl-ranked-row[data-rank="1"] .tl-ranked-label::before {{
  content: "";
  display: inline-block;
  width: 3px;
  height: 12px;
  margin-right: var(--tl-space-2);
  vertical-align: -1px;
  background: var(--tl-accent-action);
}}
.tl-ranked-value {{
  grid-area: value;
  align-self: center;
  font-family: var(--tl-font-mono);
  font-size: 15px;
  color: var(--tl-content-primary);
  font-variant-numeric: tabular-nums;
}}
.tl-ranked-sample {{
  grid-area: sample;
  font-family: var(--tl-font-mono);
  font-size: 11px;
  color: var(--tl-content-secondary);
  font-variant-numeric: tabular-nums;
}}

/* === CONTROLS — the eight interaction states (spec 10) ===
   Every selector below was observed in the live DOM on streamlit==1.50.0
   before it was written. Controls this product never renders — tabs,
   toggles, time inputs, data editors, progress bars — are deliberately
   absent: CSS for a widget that never appears is dead weight whose selector
   cannot be proven.

   DEFAULT is the state a trader sees most, so it is the quietest: the field
   surface, a hairline, nothing else. Teal appears on a field only when it is
   focused. A form of twenty inputs that each announced themselves would have
   no hierarchy left for the one thing being edited. */
[data-testid="stTextInputRootElement"],
[data-testid="stNumberInputContainer"],
[data-testid="stTextAreaRootElement"],
[data-testid="stDateInputField"],
[data-testid="stSelectbox"] [data-baseweb="select"] > div,
[data-testid="stMultiSelect"] [data-baseweb="select"] > div {{
  background: var(--tl-surface-field);
  border: 1px solid var(--tl-line-hairline);
  border-radius: var(--tl-radius-sm);
  min-height: 44px;
}}
/* HOVER is visual only. A coarse pointer never receives it, so anything that
   moved or resized here would simply not exist on a phone — and the shared
   guard in tests/test_dark_workspace.py fails any layout property inside a
   hover block. */
@media (hover: hover) and (pointer: fine) {{
  [data-testid="stTextInputRootElement"]:hover,
  [data-testid="stNumberInputContainer"]:hover,
  [data-testid="stTextAreaRootElement"]:hover,
  [data-testid="stDateInputField"]:hover,
  [data-testid="stSelectbox"] [data-baseweb="select"] > div:hover,
  [data-testid="stMultiSelect"] [data-baseweb="select"] > div:hover {{
    border-color: var(--tl-content-secondary);
  }}
}}
/* FOCUS is the one place a field goes teal, and it is never removed. Ring
   plus border, because a border alone disappears against a tag or a chosen
   value. focus-within: the element that paints the box is the wrapper, but
   the element that receives focus is the input inside it. */
[data-testid="stTextInputRootElement"]:focus-within,
[data-testid="stNumberInputContainer"]:focus-within,
[data-testid="stTextAreaRootElement"]:focus-within,
[data-testid="stDateInputField"]:focus-within,
[data-testid="stSelectbox"] [data-baseweb="select"] > div:focus-within,
[data-testid="stMultiSelect"] [data-baseweb="select"] > div:focus-within {{
  border-color: var(--tl-accent-action);
  outline: 2px solid var(--tl-accent-action);
  outline-offset: 1px;
}}
/* The number input's own steppers measured 38px. They sit inside a 44px
   container, so the floor is met by the row; giving each stepper 44px of its
   own would make one field taller than a button. */
[data-testid="stNumberInputStepUp"],
[data-testid="stNumberInputStepDown"] {{
  min-height: 44px;
  color: var(--tl-content-secondary);
  background: transparent;
}}
/* DISABLED and READ-ONLY are both un-editable, and only one is unavailable.
   Disabled recedes to the canvas — a surface *behind* the form — and takes
   the cursor with it. Read-only keeps content-primary text on the normal
   field surface, because its value is information the trader is meant to
   read. Telling them apart by opacity alone would have dimmed a real value
   to look like a forbidden one. */
[data-testid="stAppViewContainer"] input:disabled,
[data-testid="stAppViewContainer"] textarea:disabled,
[data-testid="stAppViewContainer"] button:disabled,
[data-testid="stAppViewContainer"] [aria-disabled="true"] {{
  background: var(--tl-surface-canvas);
  color: var(--tl-content-secondary);
  -webkit-text-fill-color: var(--tl-content-secondary);
  border-color: var(--tl-line-hairline);
  cursor: not-allowed;
}}
[data-testid="stAppViewContainer"] input:read-only:not(:disabled),
[data-testid="stAppViewContainer"] textarea:read-only:not(:disabled) {{
  color: var(--tl-content-primary);
  -webkit-text-fill-color: var(--tl-content-primary);
  cursor: default;
}}
/* Checkbox and slider: the target is the row a thumb hits, not the mark
   inside it. The checkbox glyph measured 24px and the slider rail 40px;
   extending the label row to 44px leaves both marks their own size. */
[data-testid="stCheckbox"] label[data-baseweb="checkbox"] {{
  min-height: 44px;
  align-items: center;
}}
[data-testid="stSlider"] [data-baseweb="slider"] {{
  min-height: 44px;
}}
[data-testid="stSlider"] [data-testid="stSliderTickBar"] {{
  color: var(--tl-content-secondary);
}}
/* A form submit measured 40px — the same floor every other button already
   had, missed because it renders outside .stButton. */
[data-testid="stFormSubmitButton"] button {{
  min-height: 44px;
}}
/* LOADING. Feedback arrives immediately and the row keeps its height, so
   nothing jumps when the spinner goes. */
[data-testid="stSpinner"] {{
  min-height: 44px;
  display: flex;
  align-items: center;
  color: var(--tl-content-secondary);
}}
/* ALERTS. One quiet ground for all four kinds, with content-primary copy.
   A tint pulls its surface toward its own hue, so semantic text on its own
   tint never clears AA at any tint strength — the pattern fails, not the
   value. The kind is carried by Streamlit's own per-kind icon and by the
   sentence itself, so colour is never the only thing saying which it is.

   Deliberately NOT differentiated by ground colour: doing that needs
   `:has()` to reach the container from the kind class inside it, and the
   container exposes its kind only through hashed `st-*` classes this repo
   does not build on. A uniform ground is also simply quieter. */
[data-testid="stAlertContainer"] {{
  background: var(--tl-surface-elevated);
  border: 1px solid var(--tl-line-hairline);
  border-radius: var(--tl-radius-md);
}}
[data-testid="stAlertContentError"],
[data-testid="stAlertContentWarning"],
[data-testid="stAlertContentInfo"],
[data-testid="stAlertContentSuccess"] {{
  color: var(--tl-content-primary);
}}
/* The dataframe toolbar. Its four buttons measured 22x22 here and 22.4 in
   the preflight — the smallest targets in the product. The icons stay their
   own size; the button grows around them, which is the whole point of the
   floor. Task 9 owns the Journal, but this is a global Streamlit control and
   the last target under 44px anywhere, so it is corrected with the rest of
   the control pass rather than left measurably broken. */
[data-testid="stElementToolbarButton"],
[data-testid="stBaseButton-elementToolbar"] {{
  min-height: 44px;
  min-width: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--tl-content-secondary);
}}
/* TOASTS sit above the page on the elevated surface, and are the one place
   a transient message is acceptable — never for a validation failure, which
   has to persist next to the field that caused it. */
[data-testid="stToastContainer"] {{
  background: var(--tl-surface-elevated);
  border: 1px solid var(--tl-line-strong);
  border-radius: var(--tl-radius-md);
  color: var(--tl-content-primary);
}}

/* === MOBILE (SP4 Phase B, <=767px) ===
   Streamlit stacks its own widgets, but our custom HTML does not: flex
   rows and HTML tables need explicit reflow. The KPI strip becomes a
   two-column compact list rather than six full-width rows, tables scroll
   inside their own frame, and touch targets reach >=44px. */
@media (max-width: 767px) {{
  /* The bottom bar appears only here, and reserves its own height plus the
     gesture-bar inset so it never covers the last row of a table. */
  .tl-mobile-nav {{
    display: flex;
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: var(--tl-z-nav);
    background: var(--tl-surface-rail);
    border-top: 1px solid var(--tl-line-hairline);
    padding-bottom: env(safe-area-inset-bottom, 0px);
  }}
  .tl-mobile-nav-item {{ position: relative; }}
  [data-testid="stAppViewContainer"] .block-container {{
    padding-bottom: calc(72px + env(safe-area-inset-bottom, 0px));
  }}
  /* The numbered rail wraps into two rows of circles at this width; the
     masthead's "Step N of 5" carries the position instead. */
  .tl-wizard-progress {{ display: none; }}
  /* Full calendar: st.columns wrap at this width, which turns a month into
     a 31-row list. Measured at 375px. The columns are told not to wrap and
     to share the row instead, so it stays a calendar. The key is the form,
     not the page — Journal and Analytics both mount the full calendar and
     both need this. Overview uses its own compact CSS grid instead. */
  .st-key-tl_full_calendar [data-testid="stHorizontalBlock"] {{
    flex-wrap: nowrap;
    gap: 2px;
  }}
  .st-key-tl_full_calendar [data-testid="stColumn"] {{
    flex: 1 1 0;
    min-width: 0;
  }}
  /* Only the horizontal padding is surrendered to fit seven columns across
     — at 375px each column is ~47px wide. The height is set outside this
     media query, because a day cell is a touch target at every width. */
  .st-key-tl_full_calendar [data-testid="stColumn"] .stButton button {{
    padding-left: 0;
    padding-right: 0;
    font-size: 12px;
  }}
  /* Clear the bottom navigation so the wizard's primary action is never
     underneath it. */
  .st-key-tl_wizard_bar {{
    bottom: calc(51px + env(safe-area-inset-bottom, 0px));
  }}
  .tl-kpi-row {{ flex-direction: column; gap: var(--tl-space-2); }}
  .tl-kpi-card {{ width: 100%; }}
  .tl-kpi-cell {{ flex: 1 1 50%; }}
  .tl-kpi-cell:nth-child(odd) {{ border-left-width: 0; }}
  .tl-kpi-cell:nth-child(n+3) {{ border-top: 1px solid var(--tl-line-hairline); }}
  .tl-kpi-figure {{ font-size: 22px; line-height: 28px; }}
  .tl-masthead {{ align-items: flex-start; flex-direction: column; gap: var(--tl-space-2); }}
  /* Anchored for the same reason as the desktop rule — unanchored, this
     lost to Streamlit's h1 sizing and the masthead never shrank on a
     phone at all. */
  [data-testid="stAppViewContainer"] .tl-masthead-title {{
    font-size: 28px;
    line-height: 34px;
  }}
  [data-testid="stAppViewContainer"] .tl-section-title {{
    font-size: 26px;
    line-height: 32px;
  }}
  .tl-finding {{ flex-direction: column; gap: var(--tl-space-2); }}
  .tl-table-wrap {{ overflow-x: auto; -webkit-overflow-scrolling: touch; }}
  .tl-table {{ min-width: 560px; }}
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
    # A ligature NAME, not a glyph: the icon is plain escaped text styled by
    # the Material Symbols font, the same convention the mobile nav already
    # proves in the browser. Emoji were the previous answer and are the wrong
    # one — they are font-dependent, carry their own colour, and cannot be
    # token-controlled (spec D9). An empty icon emits no element at all rather
    # than an empty 32px box with a margin.
    icon_html = f'<div class="icon">{escape(icon)}</div>' if str(icon).strip() else ""
    return (
        '<div class="tl-empty-card">'
        f"{img_html}"
        f"{icon_html}"
        f"<h4>{escape(title)}</h4>"
        f"<p>{escape(body)}</p>"
        f"{action_html}</div>"
    )


def render_banner(
    text: str, variant: str = "warning", *, announce: bool = False
) -> str:
    """Inline banner: warning | info | danger. Unknown variants fall back
    to warning (visible but non-alarming).

    Static guidance stays quiet to assistive technology. Callers set
    ``announce`` only for a message created by the latest interaction, such
    as blocked wizard navigation.
    """
    if variant not in _BANNER_VARIANTS:
        variant = "warning"
    role = ' role="alert"' if announce else ""
    return f'<div class="tl-banner tl-banner-{variant}"{role}>{escape(text)}</div>'


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
