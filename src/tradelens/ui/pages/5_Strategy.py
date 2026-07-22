import sys
from html import escape
from pathlib import Path

_root = str(Path(__file__).resolve().parents[4])
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st  # noqa: E402

from src.tradelens.services.strategy import (  # noqa: E402
    get_active_strategy,
    parse_list,
    parse_markets,
    parse_mistakes,
    parse_setups,
    parse_timeframes,
    upsert_strategy_profile,
)
from src.tradelens.ui.components.auth import current_user_id, require_auth  # noqa: E402
from src.tradelens.ui.components.demo_banner import render_demo_banner  # noqa: E402
from src.tradelens.ui.components.sidebar import render_sidebar  # noqa: E402
from src.tradelens.ui.components.theme import inject_css  # noqa: E402
from src.tradelens.ui.design_system import (  # noqa: E402
    get_asset_as_base64,
    inject_design_system,
    render_badge,
    render_banner,
    render_chip_row,
    render_section_header,
)

st.set_page_config(page_title="Strategy Profile")
inject_css()
inject_design_system()  # design_system.py wins ties (injected after theme)
require_auth()
uid = current_user_id()
render_demo_banner()
render_sidebar()
st.markdown(
    render_section_header(
        "Strategy Profile",
        "Define your strategy so AI analysis, journal, and grading are "
        "strategy-aware.",
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
profile = get_active_strategy(uid) if uid is not None else None

if st.session_state.pop("_strategy_saved", False):
    st.toast("Strategy Profile saved — AI reviews will now use your rules.", icon="✅")

# ── Active strategy banner (strategy_banner.png + overlay) ────────
_banner_b64 = get_asset_as_base64("strategy_banner.png")
_BANNER_STYLE = (
    (
        "background-image: linear-gradient(rgba(13,15,17,0.75), "
        f"rgba(13,15,17,0.75)), url(data:image/png;base64,{_banner_b64}); "
        "background-size: cover; background-position: center;"
    )
    if _banner_b64
    else ""
)

if profile:
    _updated = (profile.get("updated_at") or "")[:10] or "—"
    _pname = escape(str(profile.get("name") or "—"))
    st.markdown(
        f'<div class="tl-ai-card" style="{_BANNER_STYLE}">'
        '<div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">'
        f'<span style="font-size:1.35rem;font-weight:600">{_pname}</span>'
        f"{render_badge('Active', 'success')}"
        '<span style="color:var(--tl-text-muted);font-size:0.85rem;'
        f'margin-left:auto">Last updated: {escape(_updated)}</span>'
        "</div></div>",
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        render_banner(
            "No strategy profile yet. Fill this in to unlock "
            "strategy-aware AI analysis.",
            "info",
        ),
        unsafe_allow_html=True,
    )

# Primary CTA while empty; quiet secondary once a profile exists.
if st.button(
    "Use ICT/SMC Starter Template",
    key="strategy_starter",
    type="secondary" if profile else "primary",
    disabled=uid is None,
):
    upsert_strategy_profile(uid, **STARTER_TEMPLATE)
    st.toast("Starter template loaded — review and save.", icon="✅")
    st.rerun()

st.markdown("---")

# Pre-fill form with existing values; chips preview the SAVED profile.
p = profile or {}
_markets = parse_markets(p)
_tf = parse_timeframes(p)
_tf_chips = [
    f"{label} {val}"
    for label, val in (("Entry", _tf.get("entry")), ("HTF", _tf.get("htf")))
    if val
]
_setups = parse_setups(p)
_avoided = parse_list(p.get("setups_avoided"))
_mistakes = parse_mistakes(p)


def _chips(items: list, variant: str) -> None:
    if items:
        st.markdown(
            render_chip_row(items, {c: variant for c in items}),
            unsafe_allow_html=True,
        )


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
        _chips(_markets, "primary")
    with col4:
        timeframes = st.text_input(
            "Timeframes",
            value=p.get("timeframes") or "",
            placeholder="e.g. 15m, 1H, 4H",
        )
        _chips(_tf_chips, "neutral")

    st.markdown("### Rules")
    with st.expander("Entry Rules", expanded=True):
        entry_rules = st.text_area(
            "Entry Rules",
            value=p.get("entry_rules") or "",
            height=100,
            label_visibility="collapsed",
            placeholder="e.g. BOS + OB retest on 15m, CHoCH confirmation required",
        )
    with st.expander("Stop Loss Rules"):
        stop_rules = st.text_area(
            "Stop Loss Rules",
            value=p.get("stop_rules") or "",
            height=80,
            label_visibility="collapsed",
            placeholder="e.g. Behind the OB wick, no more than 10 points away",
        )
    with st.expander("Take Profit Rules"):
        take_profit_rules = st.text_area(
            "Take Profit Rules",
            value=p.get("take_profit_rules") or "",
            height=80,
            label_visibility="collapsed",
            placeholder="e.g. Next opposing OB, 50% at 1:1 R, runner to 1:3",
        )
    with st.expander("Risk Rules"):
        risk_rules = st.text_area(
            "Risk Rules",
            value=p.get("risk_rules") or "",
            height=80,
            label_visibility="collapsed",
            placeholder=(
                "e.g. Max 1% per trade, max 2 trades per session, " "1:2 R:R minimum"
            ),
        )

    st.markdown("### Setups & Filters")
    with st.expander("Setups I Trade"):
        setups_traded = st.text_area(
            "Setups I Trade",
            value=p.get("setups_traded") or "",
            height=80,
            label_visibility="collapsed",
            placeholder="e.g. OB retest, FVG fill, liquidity sweep + reversal",
        )
        _chips(_setups, "primary")
    with st.expander("Setups I Avoid"):
        setups_avoided = st.text_area(
            "Setups I Avoid",
            value=p.get("setups_avoided") or "",
            height=80,
            label_visibility="collapsed",
            placeholder="e.g. Counter-trend, news events, choppy consolidation",
        )
        _chips(_avoided, "danger")
    with st.expander("News / Session Rules"):
        news_session_rules = st.text_input(
            "News / Session Rules",
            value=p.get("news_session_rules") or "",
            label_visibility="collapsed",
            placeholder=(
                "e.g. No trades 30 min before/after high-impact news; NY AM only"
            ),
        )

    st.markdown("### Self-Awareness")
    with st.expander("Common Mistakes to Watch For"):
        common_mistakes = st.text_area(
            "Common Mistakes to Watch For",
            value=p.get("common_mistakes") or "",
            height=100,
            label_visibility="collapsed",
            placeholder="e.g. Entering too early before confirmation, revenge trading",
        )
        _chips(_mistakes, "warning")

    submitted = st.form_submit_button(
        "Save Strategy Profile", type="primary", width="stretch"
    )

if submitted:
    if uid is None:
        st.toast(
            "A database-backed account is required to save a strategy profile.",
            icon="❌",
        )
    elif not name.strip():
        st.toast("Strategy Name is required.", icon="❌")
    else:
        try:
            upsert_strategy_profile(
                uid,
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
        except Exception as exc:  # noqa: BLE001 — surface, never crash the form
            st.toast(f"Failed to save strategy profile: {exc}", icon="❌")
