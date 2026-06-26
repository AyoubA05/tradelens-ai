import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parents[4])
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st  # noqa: E402

from src.tradelens.services.strategy import (  # noqa: E402
    get_active_strategy,
    upsert_strategy_profile,
)
from src.tradelens.ui.components.auth import require_auth  # noqa: E402
from src.tradelens.ui.components.demo_banner import render_demo_banner  # noqa: E402
from src.tradelens.ui.components.sidebar import render_sidebar  # noqa: E402
from src.tradelens.ui.components.theme import inject_css  # noqa: E402
from src.tradelens.ui.components.ui import section_header  # noqa: E402

st.set_page_config(page_title="Strategy Profile")
inject_css()
require_auth()
render_demo_banner()
render_sidebar()
st.markdown(
    section_header(
        "Strategy Profile",
        "Define your strategy so AI analysis, journal, and grading are strategy-aware.",
    ),
    unsafe_allow_html=True,
)

STARTER_TEMPLATE = {
    "name": "ICT/SMC Day Trading",
    "trading_style": "ICT / SMC",
    "markets": "NQ, ES, EURUSD, GBP/USD",
    "timeframes": "15m entry, 1H/4H HTF",
    "entry_rules": (
        "Wait for HTF POI, confirm BOS or CHoCH on LTF, enter on FVG or OB retest"
    ),
    "stop_rules": "Place SL below/above the swing that caused the BOS",
    "take_profit_rules": "TP at next liquidity level or opposing HTF POI",
    "risk_rules": "Max 1% per trade, max 2 trades per session, no revenge trading",
    "setups_traded": "Liquidity Sweep + FVG, BOS + OB Retest, CHoCH Entry",
    "setups_avoided": (
        "Counter-trend without BOS, news candle entries, off-session trades"
    ),
    "common_mistakes": "FOMO entry, moving SL, off-session trades, overtrading",
}

# Load active profile (if any)
profile = get_active_strategy()

st.caption(
    "Your AI reviews become stronger when they know your exact rules. "
    "Fill this in to get strategy-aware insights."
)

if st.session_state.pop("_strategy_saved", False):
    st.markdown(
        '<div style="background:rgba(46,125,50,0.15);border:1px solid #2e7d32;'
        'border-radius:8px;padding:10px 14px;color:#7bd88f">'
        "✅ <strong>Strategy Profile saved.</strong> AI reviews will now use your "
        "rules.</div>",
        unsafe_allow_html=True,
    )

if profile:
    updated = (profile.get("updated_at") or "")[:10] or "—"
    st.markdown(
        '<div style="background:rgba(32,128,141,0.12);border:1px solid #20808D;'
        'border-radius:10px;padding:12px 14px;margin:8px 0">'
        f"✅ <strong>Active Strategy: {profile.get('name', '—')}</strong><br>"
        f"<span style='color:#B4B8BD;font-size:0.85rem'>"
        f"Markets: {profile.get('markets') or '—'} &nbsp;|&nbsp; "
        f"Timeframes: {profile.get('timeframes') or '—'} &nbsp;|&nbsp; "
        f"Last updated: {updated}</span></div>",
        unsafe_allow_html=True,
    )
else:
    st.caption("No active profile yet — use the starter template or fill the form.")

if st.button("Use ICT/SMC Starter Template", key="strategy_starter"):
    upsert_strategy_profile(**STARTER_TEMPLATE)
    st.toast("Starter template loaded — review and save.", icon="✅")
    st.rerun()

st.markdown("---")

# Pre-fill form with existing values
p = profile or {}

with st.form("strategy_form"):
    st.markdown("### Identity")
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input(
            "Strategy Name",
            value=p.get("name") or "",
            placeholder="e.g. ICT OB Strategy",
        )
    with col2:
        trading_style = st.text_input(
            "Trading Style",
            value=p.get("trading_style") or "",
            placeholder="e.g. ICT, SMC, Price Action",
        )

    col3, col4 = st.columns(2)
    with col3:
        markets = st.text_input(
            "Markets / Assets",
            value=p.get("markets") or "",
            placeholder="e.g. NQ, ES, BTCUSD, EURUSD",
        )
    with col4:
        timeframes = st.text_input(
            "Timeframes",
            value=p.get("timeframes") or "",
            placeholder="e.g. 15m, 1H, 4H",
        )

    st.markdown("### Rules")
    entry_rules = st.text_area(
        "Entry Rules",
        value=p.get("entry_rules") or "",
        height=100,
        placeholder="e.g. BOS + OB retest on 15m, CHoCH confirmation required",
    )
    stop_rules = st.text_area(
        "Stop Loss Rules",
        value=p.get("stop_rules") or "",
        height=80,
        placeholder="e.g. Behind the OB wick, no more than 10 points away",
    )
    take_profit_rules = st.text_area(
        "Take Profit Rules",
        value=p.get("take_profit_rules") or "",
        height=80,
        placeholder="e.g. Next opposing OB, 50% at 1:1 R, runner to 1:3",
    )
    risk_rules = st.text_area(
        "Risk Rules",
        value=p.get("risk_rules") or "",
        height=80,
        placeholder="e.g. Max 1% per trade, max 2 trades per session, 1:2 R:R minimum",
    )

    st.markdown("### Setups & Filters")
    setups_traded = st.text_area(
        "Setups I Trade",
        value=p.get("setups_traded") or "",
        height=80,
        placeholder="e.g. OB retest, FVG fill, liquidity sweep + reversal",
    )
    setups_avoided = st.text_area(
        "Setups I Avoid",
        value=p.get("setups_avoided") or "",
        height=80,
        placeholder="e.g. Counter-trend, news events, choppy consolidation",
    )
    news_session_rules = st.text_input(
        "News / Session Rules",
        value=p.get("news_session_rules") or "",
        placeholder="e.g. No trades 30 min before/after high-impact news; NY AM only",
    )

    st.markdown("### Self-Awareness")
    common_mistakes = st.text_area(
        "Common Mistakes to Watch For",
        value=p.get("common_mistakes") or "",
        height=100,
        placeholder="e.g. Entering too early before confirmation, revenge trading",
    )

    submitted = st.form_submit_button(
        "Save Strategy Profile", type="primary", use_container_width=True
    )

if submitted:
    if not name.strip():
        st.toast("Strategy Name is required.", icon="❌")
    else:
        try:
            upsert_strategy_profile(
                name=name.strip(),
                trading_style=trading_style.strip() or None,
                markets=markets.strip() or None,
                timeframes=timeframes.strip() or None,
                entry_rules=entry_rules.strip() or None,
                stop_rules=stop_rules.strip() or None,
                take_profit_rules=take_profit_rules.strip() or None,
                risk_rules=risk_rules.strip() or None,
                setups_traded=setups_traded.strip() or None,
                setups_avoided=setups_avoided.strip() or None,
                news_session_rules=news_session_rules.strip() or None,
                common_mistakes=common_mistakes.strip() or None,
            )
            st.session_state["_strategy_saved"] = True
            st.rerun()
        except Exception as exc:
            st.toast(f"Failed to save strategy profile: {exc}", icon="❌")
