import sys
from pathlib import Path

# parents[5] of src/tradelens/ui/pages/*.py  →  project root
_root = str(Path(__file__).resolve().parents[5])
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st  # noqa: E402

from src.tradelens.ui.components.demo_banner import render_demo_banner  # noqa: E402
from src.tradelens.ui.components.theme import (  # noqa: E402
    BORDER,
    SURFACE,
    TEAL,
    TERRA,
    TEXT_MUTED,
    TEXT_SECONDARY,
    inject_css,
)

# This is the public landing page: it renders with ZERO database access so it is
# instant and never errors on a cold/empty deploy. No DB / service imports here.

st.set_page_config(page_title="TradeLens AI", layout="wide")
inject_css()
render_demo_banner()

# ── Hero ──────────────────────────────────────────────────────────
hero_l, hero_r = st.columns([3, 2], gap="large")
with hero_l:
    st.markdown(
        "<div style=\"font-family:'Space Grotesk',sans-serif;font-size:2.5rem;"
        'font-weight:700;line-height:1.15;letter-spacing:-0.02em">'
        "Your AI trading partner that reviews every chart, grades your process, "
        "and learns your strategy.</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div style='color:{TEXT_SECONDARY};font-size:1.1rem;margin-top:14px'>"
        "Post-trade reflection and analytics for SMC/ICT day traders. "
        "Log a trade, let the AI review your screenshot and grade your process, "
        "then improve with a weekly review that remembers your corrections.</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<a href="/" target="_self" style="display:inline-block;margin-top:20px;'
        f"padding:12px 24px;background:{TEAL};color:#fff;border-radius:10px;"
        f'font-weight:600;text-decoration:none">Open the dashboard →</a>'
        f'<a href="/NewTrade" target="_self" style="display:inline-block;'
        f"margin:20px 0 0 12px;padding:12px 24px;background:{SURFACE};"
        f"border:1px solid {BORDER};color:{TEXT_SECONDARY};border-radius:10px;"
        f'font-weight:600;text-decoration:none">Log a trade</a>',
        unsafe_allow_html=True,
    )
with hero_r:
    st.markdown(
        f'<div style="background:{SURFACE};border:1px solid {BORDER};'
        'border-radius:16px;padding:24px;margin-top:8px">'
        f"<div style='color:{TEXT_MUTED};font-size:0.8rem;text-transform:uppercase;"
        "letter-spacing:0.06em'>Sample data</div>"
        "<div style=\"font-family:'JetBrains Mono',monospace;font-size:2rem;"
        f'font-weight:600;color:{TEAL};margin-top:6px">+$4,820</div>'
        f"<div style='color:{TEXT_MUTED};font-size:0.85rem'>Net P&amp;L · 60 trades · "
        "58% win rate</div>"
        f"<div style='margin-top:16px;color:{TEXT_SECONDARY};font-size:0.9rem'>"
        "Consistency score, killzone analytics, edge-leak, and an AI weekly "
        "review — all from your own journal.</div></div>",
        unsafe_allow_html=True,
    )

st.markdown("---")

# ── How it works (3 steps) ────────────────────────────────────────
st.markdown(
    "<div style=\"font-family:'Space Grotesk',sans-serif;font-size:1.5rem;"
    'font-weight:600;margin-bottom:8px">How it works</div>',
    unsafe_allow_html=True,
)
s1, s2, s3 = st.columns(3, gap="large")


def _step(col, num: str, title: str, body: str):
    with col:
        col.markdown(
            f'<div style="background:{SURFACE};border:1px solid {BORDER};'
            'border-radius:12px;padding:20px;height:100%">'
            f'<div style=\'color:{TEAL};font-family:"JetBrains Mono",monospace;'
            f"font-weight:600'>{num}</div>"
            f"<div style='font-weight:600;font-size:1.1rem;margin-top:6px'>{title}</div>"
            f"<div style='color:{TEXT_MUTED};font-size:0.9rem;margin-top:6px'>{body}"
            "</div></div>",
            unsafe_allow_html=True,
        )


_step(
    s1,
    "01",
    "Log",
    "Record the trade: entry, exit, killzone, HTF bias, setup, and a screenshot.",
)
_step(
    s2,
    "02",
    "AI reviews & grades",
    "AI reads your chart, proposes SMC/ICT labels, and grades your process "
    "against your own strategy rules.",
)
_step(
    s3,
    "03",
    "You improve",
    "A weekly review and correction memory turn repeated mistakes into rules you "
    "actually follow.",
)

st.markdown("---")

# ── Differentiation table (static HTML — teal checks for TradeLens) ──
st.markdown(
    "<div style=\"font-family:'Space Grotesk',sans-serif;font-size:1.5rem;"
    'font-weight:600;margin-bottom:8px">Why TradeLens</div>',
    unsafe_allow_html=True,
)

_YES = f'<span style="color:{TEAL};font-weight:700">✓</span>'
_NO = f'<span style="color:{TEXT_MUTED}">—</span>'


def _row(feature: str, tl: str, tz: str, ew: str, ts: str) -> str:
    return (
        f"<tr><td style='padding:10px 12px;color:{TEXT_SECONDARY}'>{feature}</td>"
        f"<td style='padding:10px 12px;text-align:center;background:{TEAL}1a'>{tl}</td>"
        f"<td style='padding:10px 12px;text-align:center'>{tz}</td>"
        f"<td style='padding:10px 12px;text-align:center'>{ew}</td>"
        f"<td style='padding:10px 12px;text-align:center'>{ts}</td></tr>"
    )


_comparison = (
    f'<table style="width:100%;border-collapse:collapse;border:1px solid {BORDER};'
    'border-radius:12px;overflow:hidden;font-size:0.92rem">'
    f"<thead><tr style='background:{SURFACE}'>"
    f"<th style='padding:10px 12px;text-align:left'>Feature</th>"
    f"<th style='padding:10px 12px;color:{TEAL}'>TradeLens</th>"
    "<th style='padding:10px 12px'>TradeZella</th>"
    "<th style='padding:10px 12px'>Edgewonk</th>"
    "<th style='padding:10px 12px'>TraderSync</th></tr></thead><tbody>"
    + _row("SMC/ICT-native fields", _YES, _NO, _NO, _NO)
    + _row("AI screenshot review", _YES, _NO, _NO, _NO)
    + _row("Grading against YOUR strategy rules", _YES, _NO, _NO, _NO)
    + _row("Correction memory (AI learns your edits)", _YES, _NO, _NO, _NO)
    + _row("Weekly AI review", _YES, _NO, _NO, _NO)
    + _row("No per-message AI caps", _YES, _NO, _NO, _NO)
    + "</tbody></table>"
)
st.markdown(_comparison, unsafe_allow_html=True)

st.markdown("---")

# ── Honest scope note ─────────────────────────────────────────────
st.markdown(
    f'<div style="background:{SURFACE};border:1px solid {TERRA};'
    'border-radius:8px;padding:14px 18px">'
    f"<span style='color:{TEXT_SECONDARY}'>"
    "<strong>Scope:</strong> TradeLens AI is a post-trade reflection journal. "
    "It does not generate signals, predictions, or trade recommendations, and it "
    "never places trades. Everything here is educational review of trades you have "
    "already taken.</span></div>",
    unsafe_allow_html=True,
)
