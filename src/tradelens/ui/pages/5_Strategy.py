import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parents[4])
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st  # noqa: E402

from src.tradelens.services.strategy import get_active_strategy, upsert_strategy_profile  # noqa: E402

st.set_page_config(page_title="Strategy Profile", page_icon="🎯")
st.title("🎯 Strategy Profile")
st.caption("Define your trading strategy so AI analysis, journal, and grading are strategy-aware.")

# Load active profile (if any)
profile = get_active_strategy()

if profile:
    st.success(f"Active profile: **{profile.get('name', '—')}** — last updated: {profile.get('updated_at', '—')[:10] if profile.get('updated_at') else '—'}")
else:
    st.info("No active strategy profile yet. Fill in the form below and click Save.")

st.markdown("---")

# Pre-fill form with existing values
p = profile or {}

with st.form("strategy_form"):
    st.markdown("### Identity")
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("Strategy Name", value=p.get("name") or "", placeholder="e.g. ICT OB Strategy")
    with col2:
        trading_style = st.text_input("Trading Style", value=p.get("trading_style") or "", placeholder="e.g. ICT, SMC, Price Action")

    col3, col4 = st.columns(2)
    with col3:
        markets = st.text_input("Markets / Assets", value=p.get("markets") or "", placeholder="e.g. NQ, ES, BTCUSD, EURUSD")
    with col4:
        timeframes = st.text_input("Timeframes", value=p.get("timeframes") or "", placeholder="e.g. 15m, 1H, 4H")

    st.markdown("### Rules")
    entry_rules = st.text_area("Entry Rules", value=p.get("entry_rules") or "", height=100,
                               placeholder="e.g. BOS + OB retest on 15m, CHoCH confirmation required")
    stop_rules = st.text_area("Stop Loss Rules", value=p.get("stop_rules") or "", height=80,
                              placeholder="e.g. Behind the OB wick, no more than 10 points away")
    take_profit_rules = st.text_area("Take Profit Rules", value=p.get("take_profit_rules") or "", height=80,
                                     placeholder="e.g. Next opposing OB, 50% at 1:1 R, runner to 1:3")
    risk_rules = st.text_area("Risk Rules", value=p.get("risk_rules") or "", height=80,
                              placeholder="e.g. Max 1% per trade, max 2 trades per session, 1:2 R:R minimum")

    st.markdown("### Setups & Filters")
    setups_traded = st.text_area("Setups I Trade", value=p.get("setups_traded") or "", height=80,
                                  placeholder="e.g. OB retest, FVG fill, liquidity sweep + reversal")
    setups_avoided = st.text_area("Setups I Avoid", value=p.get("setups_avoided") or "", height=80,
                                   placeholder="e.g. Counter-trend, news events, choppy consolidation")
    news_session_rules = st.text_input("News / Session Rules", value=p.get("news_session_rules") or "",
                                       placeholder="e.g. No trades 30 min before/after high-impact news; NY AM only")

    st.markdown("### Self-Awareness")
    common_mistakes = st.text_area("Common Mistakes to Watch For", value=p.get("common_mistakes") or "", height=100,
                                    placeholder="e.g. Entering too early before confirmation, revenge trading after losses")

    submitted = st.form_submit_button("💾 Save Strategy Profile", type="primary", use_container_width=True)

if submitted:
    if not name.strip():
        st.error("Strategy Name is required.")
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
            st.success(f"Strategy profile '{name.strip()}' saved and activated!")
            st.rerun()
        except Exception as exc:
            st.error(f"Failed to save strategy profile: {exc}")
