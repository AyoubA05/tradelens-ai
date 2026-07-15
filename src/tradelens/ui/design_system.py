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

# =========================================================================
# COLOR TOKENS (authoritative — PRODUCT.md palette)
# =========================================================================
TL_BG = "#0d0f11"
TL_SURFACE = "#13161a"
TL_SURFACE_2 = "#1a1e24"
TL_BORDER = "#252a32"
TL_BORDER_SUBTLE = "#1e2228"
TL_TEXT = "#e8eaed"
# Muted/faint brightened in Phase 9 for WCAG AA (≥4.5:1 small text):
# muted 5.4:1 on SURFACE / 5.0:1 on SURFACE_2; faint 4.7:1 on SURFACE.
TL_TEXT_MUTED = "#848d9c"
TL_TEXT_FAINT = "#79828f"
TL_PRIMARY = "#00c2b2"
TL_PRIMARY_HOVER = "#00a89a"
TL_PRIMARY_DIM = "rgba(0,194,178,0.12)"
TL_SUCCESS = "#22c55e"
TL_SUCCESS_DIM = "rgba(34,197,94,0.12)"
TL_DANGER = "#ef4444"
TL_DANGER_DIM = "rgba(239,68,68,0.12)"
TL_WARNING = "#f59e0b"
TL_WARNING_DIM = "rgba(245,158,11,0.12)"
TL_NEUTRAL = "#374151"
TL_NEUTRAL_DIM = "rgba(55,65,81,0.3)"

# Grade scale (A → F): success green through amber to danger red. The two
# intermediate steps are the same Tailwind-500 family as the semantic
# tokens above (lime-500, orange-500), so the ramp reads as one system.
TL_GRADE_A = TL_SUCCESS
TL_GRADE_B = "#84cc16"
TL_GRADE_C = TL_WARNING
TL_GRADE_D = "#f97316"
TL_GRADE_F = TL_DANGER

# =========================================================================
# TYPOGRAPHY TOKENS (body stack for headings too — owner decision)
# =========================================================================
TL_FONT_MONO = "'JetBrains Mono', 'Fira Code', monospace"
TL_FONT_BODY = "'Inter', -apple-system, sans-serif"

_FONT_IMPORT = (
    "https://fonts.googleapis.com/css2"
    "?family=Inter:wght@400;500;600;700"
    "&family=JetBrains+Mono:wght@400;600;700"
    "&display=swap"
)

# Assets generated via Higgsfield live next to this module.
ASSETS_DIR = Path(__file__).resolve().parent / "assets"

# =========================================================================
# PLOTLY TEMPLATE (single source of truth for chart theming)
# =========================================================================
# Transparent backgrounds so charts sit on whatever surface frames them
# (page background or a bordered container). Registered as the plotly
# default below, so every figure inherits this styling even when a call
# site forgets to pass `template=`.
PLOTLY_TEMPLATE = go.layout.Template(
    layout=go.Layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=TL_FONT_BODY, color=TL_TEXT, size=12),
        title=dict(font=dict(size=14, color=TL_TEXT), x=0.0, xanchor="left"),
        colorway=[
            TL_PRIMARY,
            TL_WARNING,
            TL_SUCCESS,
            TL_TEXT_MUTED,
            TL_DANGER,
            TL_NEUTRAL,
        ],
        xaxis=dict(
            gridcolor=TL_BORDER,
            zerolinecolor=TL_BORDER,
            tickfont=dict(color=TL_TEXT_MUTED, size=11),
            title=dict(font=dict(color=TL_TEXT_MUTED, size=12)),
        ),
        yaxis=dict(
            gridcolor=TL_BORDER,
            zerolinecolor=TL_BORDER,
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
@import url('{_FONT_IMPORT}');

/* === CSS VARIABLES === */
:root {{
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
  --tl-font-mono: {TL_FONT_MONO};
  --tl-font-body: {TL_FONT_BODY};
  --tl-space-1: 4px; --tl-space-2: 8px; --tl-space-3: 12px;
  --tl-space-4: 16px; --tl-space-6: 24px; --tl-space-8: 32px;
  --tl-space-12: 48px;
  --tl-radius-sm: 6px; --tl-radius-md: 10px;
  --tl-radius-lg: 16px; --tl-radius-full: 9999px;
  --tl-shadow-sm: 0 1px 3px rgba(0,0,0,0.3);
  --tl-shadow-md: 0 4px 16px rgba(0,0,0,0.4);
  --tl-shadow-lg: 0 12px 40px rgba(0,0,0,0.5);
}}

/* === BASE (proven selectors only) ===
   Page background comes from .streamlit/config.toml [theme]. */
[data-testid="stAppViewContainer"] {{
  font-family: var(--tl-font-body);
  color: var(--tl-text);
}}
/* Headings use the body stack (overrides theme.py's Space Grotesk;
   same selector, injected later, so this wins). */
[data-testid="stAppViewContainer"] h1,
[data-testid="stAppViewContainer"] h2,
[data-testid="stAppViewContainer"] h3 {{
  font-family: var(--tl-font-body);
  font-weight: 700;
  letter-spacing: -0.01em;
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
  max-width: 1200px;
}}

/* === SIDEBAR === */
[data-testid="stSidebar"] {{
  background: var(--tl-surface);
  border-right: 1px solid var(--tl-border);
}}
/* Nav links (st.page_link renders an anchor): quiet rest state, surface
   hover, visible keyboard focus. */
[data-testid="stSidebar"] a {{
  border-radius: var(--tl-radius-sm);
  transition: background 0.15s ease-out;
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
  font-weight: 600;
}}
.tl-side-note.active {{
  border-color: rgba(0,194,178,0.3);
  background: var(--tl-primary-dim);
  color: var(--tl-primary);
}}
.tl-side-note.active b {{
  color: var(--tl-primary);
}}

/* === NATIVE METRICS (proven stMetric* set; replaces the legacy
       'metric-container' selector from the spec) === */
.stMetric {{
  background: var(--tl-surface);
  border: 1px solid var(--tl-border);
  border-radius: var(--tl-radius-md);
  padding: 12px 16px;
}}
.stMetric [data-testid="stMetricValue"] {{
  font-family: var(--tl-font-mono);
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  color: var(--tl-text);
}}
.stMetric [data-testid="stMetricDelta"] {{
  font-family: var(--tl-font-mono);
}}
.stMetric [data-testid="stMetricLabel"] {{
  color: var(--tl-text-muted);
}}

/* === BUTTONS (all states: rest, hover, focus, active) ===
   Form submit buttons (Sign In, Save Trade, …) are primary actions too —
   they get the identical treatment as .stButton. */
.stButton > button,
.stFormSubmitButton > button {{
  background: var(--tl-primary);
  color: #ffffff;
  border: 1px solid var(--tl-primary);
  border-radius: var(--tl-radius-sm);
  font-weight: 600;
  transition: background 0.15s ease-out, box-shadow 0.15s ease-out;
}}
@media (hover: hover) and (pointer: fine) {{
  .stButton > button:hover,
  .stFormSubmitButton > button:hover {{
    background: var(--tl-primary-hover);
    border-color: var(--tl-primary-hover);
    box-shadow: 0 0 16px var(--tl-primary-dim);
  }}
}}
.stButton > button:focus-visible,
.stFormSubmitButton > button:focus-visible {{
  outline: 2px solid var(--tl-primary);
  outline-offset: 2px;
}}
.stButton > button:active,
.stFormSubmitButton > button:active {{
  background: var(--tl-primary-hover);
}}

/* === KPI CARD === */
.tl-kpi-card {{
  background: var(--tl-surface);
  border: 1px solid var(--tl-border);
  border-radius: var(--tl-radius-md);
  padding: var(--tl-space-4);
  box-shadow: var(--tl-shadow-sm);
}}
.tl-kpi-label {{
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--tl-text-muted);
}}
.tl-kpi-value {{
  font-size: 26px;
  font-weight: 700;
  font-family: var(--tl-font-mono);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
  white-space: nowrap;
  color: var(--tl-text);
  line-height: 1.1;
  margin-top: 4px;
}}
.tl-kpi-value.positive {{ color: var(--tl-success); }}
.tl-kpi-value.negative {{ color: var(--tl-danger); }}
.tl-kpi-value.missing {{ color: var(--tl-text-muted); }}
.tl-kpi-delta {{
  font-size: 12px;
  font-family: var(--tl-font-mono);
  margin-top: 2px;
  color: var(--tl-text-muted);
}}
.tl-kpi-delta.positive {{ color: var(--tl-success); }}
.tl-kpi-delta.negative {{ color: var(--tl-danger); }}

/* === INSIGHT CARD ===
   Variants use tinted backgrounds + accent icon (NO colored side
   borders — PRODUCT.md anti-pattern; owner decision 2026-07-06). */
.tl-insight-card {{
  background: var(--tl-surface);
  border: 1px solid var(--tl-border);
  border-radius: var(--tl-radius-md);
  padding: var(--tl-space-4);
}}
.tl-insight-card.strength {{ background: var(--tl-success-dim); }}
.tl-insight-card.leak {{ background: var(--tl-danger-dim); }}
.tl-insight-card.neutral {{ background: var(--tl-neutral-dim); }}
.tl-insight-head {{
  display: flex;
  align-items: center;
  gap: var(--tl-space-2);
  margin-bottom: var(--tl-space-2);
}}
.tl-insight-icon {{ font-size: 16px; }}
.tl-insight-card.strength .tl-insight-icon {{ color: var(--tl-success); }}
.tl-insight-card.leak .tl-insight-icon {{ color: var(--tl-danger); }}
.tl-insight-card.neutral .tl-insight-icon {{ color: var(--tl-text-muted); }}
.tl-insight-title {{
  font-size: 14px;
  font-weight: 600;
  color: var(--tl-text);
  flex: 1;
}}
.tl-insight-body {{
  font-size: 13px;
  color: var(--tl-text);
  margin: 0 0 var(--tl-space-2) 0;
}}
.tl-insight-evidence {{
  font-size: 12px;
  color: var(--tl-text-muted);
  margin: 0;
}}

/* === AI CARD === */
.tl-ai-card {{
  background: var(--tl-surface);
  border: 1px solid var(--tl-primary);
  border-radius: var(--tl-radius-md);
  padding: var(--tl-space-4);
  position: relative;
}}
.tl-ai-card::before {{
  content: 'AI';
  position: absolute;
  top: var(--tl-space-2);
  right: var(--tl-space-3);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.12em;
  color: var(--tl-primary);
  opacity: 0.7;
}}

/* === FORM SECTION CARD === */
.tl-form-card {{
  background: var(--tl-surface);
  border: 1px solid var(--tl-border);
  border-radius: var(--tl-radius-md);
  padding: var(--tl-space-6);
  margin-bottom: var(--tl-space-4);
}}
.tl-form-card h3 {{
  font-size: 14px;
  font-weight: 600;
  color: var(--tl-text);
  margin-bottom: var(--tl-space-4);
}}

/* === EMPTY STATE CARD === */
.tl-empty-card {{
  background: var(--tl-surface);
  border: 1px dashed var(--tl-border);
  border-radius: var(--tl-radius-lg);
  padding: var(--tl-space-12) var(--tl-space-8);
  text-align: center;
}}
.tl-empty-card .icon {{
  font-size: 32px;
  margin-bottom: var(--tl-space-3);
  opacity: 0.4;
}}
.tl-empty-card h4 {{
  font-size: 14px;
  font-weight: 600;
  color: var(--tl-text-muted);
  margin-bottom: var(--tl-space-2);
}}
.tl-empty-card p {{
  font-size: 12px;
  color: var(--tl-text-faint);
  max-width: 280px;
  margin: 0 auto;
}}
.tl-empty-img {{
  max-width: 280px;
  width: 100%;
  border-radius: var(--tl-radius-md);
  margin-bottom: var(--tl-space-4);
}}
.tl-empty-action {{
  margin-top: var(--tl-space-3);
  font-size: 13px;
  font-weight: 600;
  color: var(--tl-primary);
}}

/* === BADGES / CHIPS === */
.tl-badge {{
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: var(--tl-radius-full);
  font-size: 11px;
  font-weight: 500;
}}
.tl-badge-success {{ background: var(--tl-success-dim); color: var(--tl-success); }}
.tl-badge-danger {{ background: var(--tl-danger-dim); color: var(--tl-danger); }}
.tl-badge-warning {{ background: var(--tl-warning-dim); color: var(--tl-warning); }}
.tl-badge-primary {{ background: var(--tl-primary-dim); color: var(--tl-primary); }}
.tl-badge-neutral {{
  background: var(--tl-neutral-dim);
  color: var(--tl-text-muted);
}}
.tl-confidence-high {{
  background: var(--tl-success-dim);
  color: var(--tl-success);
}}
.tl-confidence-medium {{
  background: var(--tl-warning-dim);
  color: var(--tl-warning);
}}
.tl-confidence-low {{
  background: var(--tl-neutral-dim);
  color: var(--tl-text-muted);
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
  margin: var(--tl-space-6) 0 var(--tl-space-4) 0;
}}
.tl-section-header::before {{
  content: '';
  display: block;
  width: 20px;
  height: 2px;
  border-radius: 1px;
  background: var(--tl-primary);
  margin-bottom: var(--tl-space-2);
}}
.tl-section-title {{
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--tl-text);
}}
.tl-section-subtitle {{
  font-size: 13px;
  color: var(--tl-text-muted);
  margin-top: 2px;
}}
/* Chart card title (analytics) — one quiet weight below section titles. */
.tl-chart-title {{
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.01em;
  color: var(--tl-text);
  margin: 0 0 var(--tl-space-2) 0;
}}

/* === BANNERS === */
.tl-banner {{
  border-radius: var(--tl-radius-sm);
  padding: var(--tl-space-3) var(--tl-space-4);
  font-size: 13px;
  margin-bottom: var(--tl-space-4);
}}
.tl-banner-warning {{
  background: var(--tl-warning-dim);
  color: var(--tl-warning);
  border: 1px solid rgba(245,158,11,0.25);
}}
.tl-banner-info {{
  background: var(--tl-primary-dim);
  color: var(--tl-primary);
  border: 1px solid rgba(0,194,178,0.25);
}}
.tl-banner-danger {{
  background: var(--tl-danger-dim);
  color: var(--tl-danger);
  border: 1px solid rgba(239,68,68,0.25);
}}

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
.tl-step-circle.done {{ background: var(--tl-primary); color: #fff; }}
.tl-step-circle.active {{
  background: var(--tl-primary);
  color: #fff;
  box-shadow: 0 0 0 3px var(--tl-primary-dim);
}}
.tl-step-circle.future {{
  background: var(--tl-border);
  color: var(--tl-text-muted);
}}
.tl-step-label {{
  font-size: 11px;
  color: var(--tl-text-muted);
  margin-top: 4px;
}}
.tl-step-connector {{
  flex: 1;
  height: 2px;
  margin-bottom: 16px;
}}
.tl-step-connector.done {{ background: var(--tl-primary); }}
.tl-step-connector.future {{ background: var(--tl-border); }}

/* === QUICK ACTION CARD (rest, hover, focus-within states) === */
.tl-action-card {{
  display: block;
  background: var(--tl-surface);
  border: 1px solid var(--tl-border);
  border-radius: var(--tl-radius-md);
  padding: var(--tl-space-4);
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}}
@media (hover: hover) and (pointer: fine) {{
  .tl-action-card:hover {{
    border-color: var(--tl-primary);
    box-shadow: var(--tl-shadow-md);
  }}
}}
.tl-action-card:focus-within {{
  border-color: var(--tl-primary);
  box-shadow: var(--tl-shadow-md);
}}

/* === HERO KPI ROW (dashboard) ===
   Background image is set inline (data URI + rgba(13,15,17,0.65) overlay)
   because the asset is embedded per-page via get_asset_as_base64(). */
.tl-hero-wrap {{
  border: 1px solid var(--tl-border);
  border-radius: var(--tl-radius-lg);
  padding: var(--tl-space-6);
  margin-bottom: var(--tl-space-4);
  background-color: var(--tl-surface);
  background-size: cover;
  background-position: center;
}}
.tl-kpi-row {{
  display: flex;
  gap: var(--tl-space-3);
  flex-wrap: wrap;
}}
.tl-kpi-row .tl-kpi-card {{
  flex: 1 1 150px;
  min-width: 150px;
  background: rgba(19, 22, 26, 0.78);
}}

/* === DATA TABLE (recent trades etc.) === */
.tl-table-wrap {{ overflow-x: auto; }}
.tl-table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}}
.tl-table th {{
  text-align: left;
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--tl-text-muted);
  padding: 10px var(--tl-space-3);
  border-bottom: 1px solid var(--tl-border);
}}
.tl-table td {{
  padding: 10px var(--tl-space-3);
  border-bottom: 1px solid var(--tl-border-subtle);
  color: var(--tl-text);
  transition: background 0.15s ease-out;
}}
.tl-table td.mono {{
  font-family: var(--tl-font-mono);
  font-variant-numeric: tabular-nums;
}}
.tl-table th.num, .tl-table td.num {{ text-align: right; }}
.tl-table td.pnl-pos {{ color: var(--tl-success); }}
.tl-table td.pnl-neg {{ color: var(--tl-danger); }}
.tl-table tr:hover td {{ background: var(--tl-surface-2); }}

/* === WELCOME (dashboard first-run empty state) === */
.tl-welcome {{
  text-align: center;
  padding: var(--tl-space-8) 0;
}}
.tl-welcome-img {{
  width: 100%;
  border-radius: var(--tl-radius-lg);
  margin-bottom: var(--tl-space-6);
}}
.tl-welcome-title {{
  font-size: 24px;
  font-weight: 700;
  color: var(--tl-text);
  margin: 0 0 var(--tl-space-2) 0;
}}
.tl-welcome-sub {{
  font-size: 14px;
  color: var(--tl-text-muted);
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
  font-weight: 600;
  color: var(--tl-text);
  margin-bottom: 2px;
}}
.tl-action-sub {{
  display: block;
  font-size: 12px;
  color: var(--tl-text-muted);
  margin-bottom: var(--tl-space-2);
}}
.tl-action-go {{
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: var(--tl-primary);
}}

/* === STREAMLIT CHROME ===
   Config-first: deploy button / dev toolbar hidden via
   client.toolbarMode = "minimal" in .streamlit/config.toml (documented
   option, valid on pinned 1.50.0). Intentionally NO CSS rules for
   stToolbar / stDecoration / metric-container — those selectors are not
   proven in this repo. */

/* === INLINE CODE (markdown) ===
   Streamlit's default renders code spans red — red is reserved for
   errors. Recolor onto the brand teal over an elevated surface. */
[data-testid="stAppViewContainer"] code {{
  color: var(--tl-primary);
  background: var(--tl-surface-2);
  border-radius: 4px;
}}

/* === AI REVIEW BODY (Insights & Review) ===
   The model's markdown ## / ### headings must sit BELOW the page's
   18px section titles — inside the keyed tl_review_* containers they
   render at body-plus scale instead of full H2/H3 size. */
[class*="st-key-tl_review_"] h1,
[class*="st-key-tl_review_"] h2,
[class*="st-key-tl_review_"] h3 {{
  font-size: 1.05rem;
  font-weight: 600;
  padding-top: var(--tl-space-2);
  padding-bottom: 0;
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
  background: var(--tl-text-muted);
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
  color: var(--tl-text-muted);
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
  background: var(--tl-text-muted);
  display: inline-block;
}}
.tl-cal-dot.positive {{ background: var(--tl-success); }}
.tl-cal-dot.negative {{ background: var(--tl-danger); }}

/* === MOTION (accessibility — PRODUCT.md) === */
@media (prefers-reduced-motion: reduce) {{
  .tl-action-card,
  .stButton > button,
  .tl-table td,
  [data-testid="stSidebar"] a {{
    transition: none;
  }}
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
    sub = (
        f'<div class="tl-section-subtitle">{escape(subtitle)}</div>' if subtitle else ""
    )
    return (
        '<div class="tl-section-header">'
        f'<div class="tl-section-title">{escape(title)}</div>'
        f"{sub}</div>"
    )


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
