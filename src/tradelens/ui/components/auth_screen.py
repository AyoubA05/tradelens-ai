"""
SP3 — presentation for the pre-login auth screen.

Split out of auth.py, which keeps all logic (tokens, bcrypt, signup rules).
This module owns every pixel: the focused card, its scoped CSS, the backdrop,
and the motion. Scoped .tl-auth-* selectors only — styling bare tags breaks
Streamlit widgets and contrast.
"""

from __future__ import annotations

from html import escape

from src.tradelens.ui.design_system import (
    TL_BG,
    TL_BORDER,
    TL_DANGER,
    TL_DANGER_DIM,
    TL_PRIMARY,
    TL_SURFACE,
    TL_TEXT,
    TL_TEXT_MUTED,
    get_asset_as_base64,
)

# Marketing-site URL (same placeholder drill as site/main.js APP_URL).
SITE_URL = "https://www.tradelens-ai.example"  # TODO: swap at deploy

_EASE = "cubic-bezier(0.16, 1, 0.3, 1)"

_LOGO_SVG = (
    '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" '
    f'stroke="{TL_PRIMARY}" stroke-width="1.6" stroke-linecap="round" '
    'stroke-linejoin="round" aria-hidden="true">'
    '<circle cx="12" cy="12" r="9"/>'
    '<path d="M8 14.5V11"/><path d="M12 15.5V8.5"/><path d="M16 13V10"/>'
    "</svg>"
)


def auth_css() -> str:
    """Scoped styles for the focused auth card."""
    bg = get_asset_as_base64("auth_bg.webp")
    backdrop = (
        f"background-image:url(data:image/webp;base64,{bg});"
        if bg
        else f"background-color:{TL_BG};"
    )
    return f"""<style>
/* SP3 auth screen — scoped .tl-auth-* only. */
.tl-auth-bg {{
  position: fixed; inset: 0; z-index: 0;
  {backdrop}
  background-size: cover; background-position: 62% center;
  opacity: 0.28;
}}
.tl-auth-scrim {{
  position: fixed; inset: 0; z-index: 0;
  /* Token-derived, not the marketing site's #0d1117 — the app palette is
     TL_BG. Mixing the two palettes is exactly the drift SP3 removes. */
  background: linear-gradient(180deg, {TL_BG}d1, {TL_BG} 92%);
}}
.tl-auth-card {{
  position: relative; z-index: 1;
  max-width: 420px; margin: 6vh auto 0;
  background: {TL_SURFACE};
  border: 1px solid {TL_BORDER};
  border-radius: 16px;
  padding: 30px 30px 22px;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.55);
}}
.tl-auth-brand {{ display: flex; align-items: center; gap: 10px; }}
.tl-auth-word {{ font-weight: 700; font-size: 1.05rem; color: {TL_TEXT};
  letter-spacing: -0.01em; }}
.tl-auth-word em {{ font-style: normal; color: {TL_PRIMARY}; }}
.tl-auth-title {{ font-size: 1.5rem; font-weight: 700; color: {TL_TEXT};
  letter-spacing: -0.02em; margin: 18px 0 4px; }}
.tl-auth-sub {{ color: {TL_TEXT_MUTED}; font-size: 0.9rem; margin-bottom: 18px; }}
.tl-auth-err {{
  margin-top: 12px; padding: 10px 13px; border-radius: 9px;
  border: 1px solid {TL_DANGER}59; background: {TL_DANGER_DIM};
  color: {TL_TEXT}; font-size: 0.85rem; line-height: 1.45;
}}
.tl-auth-note {{
  margin-top: 18px; padding-top: 14px; border-top: 1px solid {TL_BORDER};
  color: {TL_TEXT_MUTED}; font-size: 0.78rem; line-height: 1.5;
}}
.tl-auth-note b {{ color: {TL_TEXT}; font-weight: 600; }}
.tl-auth-back {{ display: inline-block; margin-top: 10px; color: {TL_TEXT_MUTED};
  font-size: 0.78rem; text-decoration: none; }}
.tl-auth-back:hover {{ color: {TL_PRIMARY}; }}
@media (max-width: 640px) {{
  .tl-auth-card {{ margin: 2vh 16px 0; padding: 24px 20px 18px; }}
}}
@media (prefers-reduced-motion: no-preference) {{
  .tl-auth-card {{ animation: tl-auth-in 250ms {_EASE} both; }}
  @keyframes tl-auth-in {{
    from {{ opacity: 0; transform: scale(0.98); }}
    to   {{ opacity: 1; transform: none; }}
  }}
  .tl-auth-err {{ animation: tl-auth-fade 200ms {_EASE} both; }}
  @keyframes tl-auth-fade {{
    from {{ opacity: 0; }}
    to   {{ opacity: 1; }}
  }}
}}
</style>"""


def brand_html(logo_b64: str = "") -> str:
    """Compact brand lockup for the card header."""
    mark = (
        f'<img src="data:image/png;base64,{logo_b64}" alt="" width="26" height="26" '
        'style="border-radius:6px;display:block" />'
        if logo_b64
        else _LOGO_SVG
    )
    return (
        f'<div class="tl-auth-brand">{mark}'
        '<span class="tl-auth-word">TradeLens&nbsp;<em>AI</em></span></div>'
    )


def compliance_html() -> str:
    """Scope note. Copy is load-bearing (CLAUDE.md) — do not reword."""
    return (
        '<div class="tl-auth-note"><b>Reflection only.</b> TradeLens reviews the '
        "trade you already took. It does not generate signals, predictions, or "
        "trade advice."
        f'<br><a class="tl-auth-back" href="{escape(SITE_URL)}">'
        "&larr; Back to tradelens-ai.com</a></div>"
    )
