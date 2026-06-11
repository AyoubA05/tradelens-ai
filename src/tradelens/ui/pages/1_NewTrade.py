import sys
from pathlib import Path

# parents[4] of src/tradelens/ui/pages/1_NewTrade.py  →  project root
_root = str(Path(__file__).resolve().parents[4])
if _root not in sys.path:
    sys.path.insert(0, _root)

import datetime

import streamlit as st

from src.tradelens.services.screenshot_service import save_screenshot
from src.tradelens.services.trade_service import create_trade

st.set_page_config(page_title="New Trade", page_icon="📝")
st.title("📝 New Trade")

EMOTION_OPTIONS = ["Calm", "Confident", "Anxious", "FOMO", "Fearful", "Revenge", "Neutral"]

with st.form("new_trade_form"):

    # ═══════════════════════════════════════════════════════════════
    # REQUIRED TRADE LOG
    # ═══════════════════════════════════════════════════════════════
    st.markdown("### Required Trade Log")
    left, right = st.columns(2)

    # ── Left: Context + Setup ─────────────────────────────────────
    with left:
        st.markdown("**Context**")
        trade_date = st.date_input("Trade Date", value=datetime.date.today())
        entry_time = st.time_input("Entry Time")
        asset = st.text_input("Asset", placeholder="NQ, BTCUSD, EURUSD")
        session = st.selectbox("Session", ["London", "NY AM", "NY PM", "Asia", "Overlap"])
        killzone = st.selectbox(
            "Killzone",
            [
                "London Open", "New York AM", "London Close",
                "New York Lunch", "New York PM", "Asian", "Off-Session",
            ],
        )
        timeframe = st.selectbox("Timeframe", ["1m", "5m", "15m", "1H", "4H", "Daily"])
        direction = st.radio("Direction", ["Long", "Short"], horizontal=True)

        st.markdown("")
        st.markdown("**Setup**")
        htf_bias = st.selectbox("HTF Bias", ["Bullish", "Bearish", "Neutral"])
        bias = st.selectbox("Trade Bias / LTF Bias", ["Bullish", "Bearish", "Neutral"])
        setup_type = st.multiselect(
            "Setup Type",
            ["FVG", "Order Block", "BOS", "CHoCH", "Liquidity Sweep", "S/R Bounce", "Other"],
        )
        confirmation_used = st.selectbox(
            "Confirmation Used",
            [
                "Liquidity Sweep", "BOS", "CHoCH", "MSS", "FVG Fill",
                "OB Reaction", "S/R Rejection", "VWAP Reaction",
                "Candle Close", "No Confirmation",
            ],
        )

    # ── Right: Risk / Result ──────────────────────────────────────
    with right:
        st.markdown("**Risk / Result**")
        entry_price = st.number_input("Entry Price", min_value=0.0, step=0.01, format="%.4f")
        stop_price  = st.number_input("Stop Price",  min_value=0.0, step=0.01, format="%.4f")
        tp_price    = st.number_input("TP Price",    min_value=0.0, step=0.01, format="%.4f")
        exit_price  = st.number_input("Exit Price",  min_value=0.0, step=0.01, format="%.4f")
        result      = st.selectbox("Result", ["Win", "Loss", "Breakeven"])
        pnl         = st.number_input("P&L ($)", step=0.01, format="%.2f")
        mistake_tag = st.selectbox(
            "Mistake Tag",
            [
                "None", "Early Entry", "Late Entry", "Bad Stop Placement",
                "Moved Stop", "Closed Too Early", "FOMO", "Revenge Trade",
                "News Trade", "Overtrading", "Against HTF Bias",
            ],
        )
        followed_rules = st.selectbox("Followed Rules?", ["Yes", "No", "Partial"])

    # ═══════════════════════════════════════════════════════════════
    # ADVANCED SETUP CONTEXT  (collapsed)
    # ═══════════════════════════════════════════════════════════════
    with st.expander("Advanced Setup Context", expanded=False):
        adv_left, adv_right = st.columns(2)
        with adv_left:
            asset_class  = st.selectbox("Asset Class", ["Futures", "Crypto", "Forex", "Stocks"])
            htf_timeframe = st.selectbox("HTF Bias Timeframe", ["Weekly", "Daily", "4H", "1H"])
            strategy_used = st.text_input("Strategy Used")
        with adv_right:
            position_size = st.number_input("Position Size", min_value=0.0, step=0.01)
            risk_amount   = st.number_input("Risk ($)", min_value=0.0, step=0.01)
            exit_reason   = st.selectbox(
                "Exit Reason",
                [
                    "Hit TP", "Hit SL", "Manual Exit", "Breakeven Stop",
                    "Trailing Stop", "Closed Early", "Other",
                ],
            )

    # ═══════════════════════════════════════════════════════════════
    # PSYCHOLOGY & NOTES  (collapsed)
    # ═══════════════════════════════════════════════════════════════
    with st.expander("Psychology & Notes", expanded=False):
        em_col1, em_col2, em_col3 = st.columns(3)
        with em_col1:
            emotions_before = st.selectbox("Emotions Before", EMOTION_OPTIONS)
        with em_col2:
            emotions_during = st.selectbox("Emotions During", EMOTION_OPTIONS)
        with em_col3:
            emotions_after = st.selectbox("Emotions After", EMOTION_OPTIONS)
        notes = st.text_area("Notes", height=120)

    # ── Screenshot upload (preview before submit) ─────────────────
    screenshot_file = st.file_uploader(
        "Upload Chart Screenshot",
        type=["png", "jpg", "jpeg"],
    )
    if screenshot_file is not None:
        st.image(screenshot_file, caption="Uploaded screenshot", use_column_width=True)

    submitted = st.form_submit_button("Save Trade", type="primary", use_container_width=True)

# ── Validation + Save ─────────────────────────────────────────────
if submitted:
    errors = []
    if not asset.strip():
        errors.append("Asset cannot be empty.")
    if entry_price <= 0:
        errors.append("Entry price must be greater than 0.")
    if stop_price <= 0:
        errors.append("Stop price must be greater than 0.")
    if exit_price <= 0:
        errors.append("Exit price must be greater than 0.")
    if not result:
        errors.append("Result must be selected.")
    if direction == "Long" and stop_price >= entry_price:
        errors.append("Long trade: stop price must be below entry price.")
    if direction == "Short" and stop_price <= entry_price:
        errors.append("Short trade: stop price must be above entry price.")

    if errors:
        for err in errors:
            st.error(err)
    else:
        # DB-backed fields only. UI-only fields (entry_time, killzone, htf_bias,
        # htf_timeframe, confirmation_used, exit_reason, mistake_tag, followed_rules)
        # have no Trade model column yet and are intentionally excluded.
        trade_data = {
            "trade_date":      str(trade_date),
            "asset":           asset.strip(),
            "asset_class":     asset_class,
            "session":         session,
            "timeframe":       timeframe,
            "direction":       direction,
            "bias":            bias,
            "setup_type":      ", ".join(setup_type) if setup_type else None,
            "entry_price":     entry_price,
            "stop_price":      stop_price,
            "tp_price":        tp_price,
            "exit_price":      exit_price,
            "position_size":   position_size,
            "risk_amount":     risk_amount,
            "result":          result,
            "pnl":             pnl,
            "strategy_used":   strategy_used or None,
            "emotions_before": emotions_before,
            "emotions_during": emotions_during,
            "emotions_after":  emotions_after,
            "notes":           notes or None,
        }
        try:
            trade = create_trade(trade_data)
            st.success(f"✅ Trade saved! ID: {trade.id}")
            st.balloons()
        except Exception as e:
            st.error(str(e))
        else:
            if screenshot_file is not None:
                try:
                    screenshot = save_screenshot(trade.id, screenshot_file)
                    st.success(f"Screenshot saved to {screenshot.file_path}")
                except Exception as exc:
                    st.warning(f"Trade saved but screenshot upload failed: {exc}")
