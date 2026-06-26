import sys
from pathlib import Path

# parents[4] of src/tradelens/ui/pages/1_NewTrade.py  →  project root
_root = str(Path(__file__).resolve().parents[4])
if _root not in sys.path:
    sys.path.insert(0, _root)

import datetime  # noqa: E402
import json  # noqa: E402

import streamlit as st  # noqa: E402

from src.tradelens.services.screenshot_service import (  # noqa: E402
    save_screenshot,
    save_screenshot_url,
)
from src.tradelens.services.strategy import get_active_strategy  # noqa: E402
from src.tradelens.services.trade_service import (  # noqa: E402
    create_trade,
    find_recent_duplicate,
)
from src.tradelens.ui.components.auth import current_user_id, require_auth  # noqa: E402
from src.tradelens.ui.components.demo_banner import render_demo_banner  # noqa: E402
from src.tradelens.ui.components.sidebar import render_sidebar  # noqa: E402
from src.tradelens.ui.components.theme import inject_css  # noqa: E402
from src.tradelens.ui.components.ui import section_header  # noqa: E402
from src.tradelens.utils.format import humanize  # noqa: E402

st.set_page_config(page_title="New Trade")
inject_css()
require_auth()
render_demo_banner()
render_sidebar()
st.markdown(
    section_header("New Trade", "Log a completed trade for review"),
    unsafe_allow_html=True,
)

# ── Options ───────────────────────────────────────────────────────
KILLZONE_KEYS = ["asia", "london_open", "ny_am", "ny_lunch", "ny_pm", "off_session"]
TIMEFRAMES = ["1m", "5m", "15m", "1H", "4H", "D"]
SETUP_OPTIONS = [
    "FVG",
    "Order Block",
    "BOS",
    "CHoCH",
    "Liquidity Sweep",
    "S/R Bounce",
    "Other",
]
CONFLUENCES = [
    "Liquidity Sweep",
    "FVG",
    "Order Block",
    "BOS",
    "CHoCH",
    "VWAP",
    "S/R Rejection",
    "HTF POI",
]
MISTAKE_OPTIONS = [
    "None",
    "FOMO Entry",
    "Moved SL",
    "Overtraded",
    "Took Revenge Trade",
    "Ignored HTF Bias",
    "Off Session Trade",
    "Other",
]
EMOTIONS = ["Calm", "Confident", "Focused", "Anxious", "FOMO", "Revenge", "Neutral"]


def _killzone_from_time(t: datetime.time) -> str:
    """Auto-detect the ICT killzone key from an entry time (spec mapping)."""
    minutes = t.hour * 60 + t.minute
    if minutes < 8 * 60 + 30:
        return "asia"
    if minutes < 10 * 60 + 30:
        return "london_open"
    if minutes < 12 * 60:
        return "ny_am"
    if minutes < 14 * 60:
        return "ny_lunch"
    if minutes < 16 * 60 + 30:
        return "ny_pm"
    return "off_session"


# ── Strategy Profile autofill ─────────────────────────────────────
_strategy = get_active_strategy()
_markets = (_strategy or {}).get("markets") or ""
_tf_pref = (_strategy or {}).get("timeframes") or ""
if _strategy:
    st.caption(f"Defaults from Strategy Profile: **{_strategy.get('name', '—')}**")

_tf_default = next((i for i, tf in enumerate(TIMEFRAMES) if tf in _tf_pref), 1)

# ── Tabs (steps) ──────────────────────────────────────────────────
tabs = st.tabs(
    [
        "1 · Timing",
        "2 · Market Context",
        "3 · Setup",
        "4 · Risk & Outcome",
        "5 · Psychology",
        "6 · Screenshot",
    ]
)

# ── Step 1 — Trade Timing ─────────────────────────────────────────
with tabs[0]:
    c1, c2, c3 = st.columns(3)
    with c1:
        trade_date = st.date_input("Trade Date", value=datetime.date.today())
    with c2:
        entry_time = st.time_input("Entry Time", key="nt_entry_time")
    # Auto-detect killzone from entry_time; keep the selectbox in sync until the
    # user overrides it (we only push the auto value when entry_time changes).
    auto_kz = _killzone_from_time(entry_time)
    if st.session_state.get("_nt_last_auto_kz") != auto_kz:
        st.session_state["_nt_last_auto_kz"] = auto_kz
        st.session_state["nt_killzone"] = auto_kz
    with c3:
        killzone = st.selectbox(
            "Killzone (auto-detected)",
            KILLZONE_KEYS,
            format_func=humanize,
            key="nt_killzone",
        )

# ── Step 2 — Market Context ───────────────────────────────────────
with tabs[1]:
    m1, m2 = st.columns(2)
    with m1:
        asset = st.text_input(
            "Asset", placeholder=_markets or "e.g., NQ, ES, EURUSD", key="nt_asset"
        )
        asset_class = st.selectbox(
            "Asset Class", ["Futures", "Forex", "Crypto", "Stocks"], key="nt_class"
        )
        session = st.selectbox(
            "Session", ["London", "New York", "Asian", "Overlap"], key="nt_session"
        )
        direction = st.selectbox("Direction", ["Long", "Short"], key="nt_direction")
    with m2:
        timeframe = st.selectbox(
            "Timeframe", TIMEFRAMES, index=_tf_default, key="nt_timeframe"
        )
        htf_bias = st.selectbox(
            "HTF Bias", ["Bullish", "Bearish", "Neutral"], key="nt_htf"
        )
        ltf_bias = st.selectbox(
            "LTF Bias", ["Bullish", "Bearish", "Neutral"], key="nt_ltf"
        )

# ── Step 3 — Setup & Confirmation ─────────────────────────────────
with tabs[2]:
    setup_type = st.selectbox("Setup Type", SETUP_OPTIONS, key="nt_setup")
    confirmation_model = st.text_input(
        "Confirmation Model", placeholder="e.g., FVG + BOS", key="nt_confirm"
    )
    confluences = st.multiselect("Confluences", CONFLUENCES, key="nt_confluences")
    followed_rules = st.radio(
        "Followed your rules?",
        ["Yes", "No", "Partial"],
        horizontal=True,
        key="nt_rules",
    )
    mistake_tag = st.selectbox("Mistake Tag", MISTAKE_OPTIONS, key="nt_mistake")
    mistake_other = ""
    if mistake_tag == "Other":
        mistake_other = st.text_input("Describe the mistake", key="nt_mistake_other")

# ── Step 4 — Risk & Outcome (Section 3) ───────────────────────────
with tabs[3]:
    st.markdown("#### 📊 Risk & Outcome")
    st.caption(
        "Price levels are used to calculate your planned and realized R-multiple."
    )
    skip_prices = st.checkbox(
        "Skip price levels — enter P&L and R manually", key="nt_skip_prices"
    )

    entry_price = stop_price = tp_price = exit_price = None
    position_size = risk_amount = None
    manual_r = None

    if skip_prices:
        rc1, rc2, rc3 = st.columns(3)
        with rc1:
            result = st.selectbox(
                "Result", ["Win", "Loss", "Breakeven"], key="nt_result_m"
            )
        with rc2:
            pnl = st.number_input(
                "P&L ($)", value=None, placeholder="e.g., 250.00", key="nt_pnl_m"
            )
        with rc3:
            manual_r = st.number_input(
                "Realized R", value=None, placeholder="e.g., 2.0", key="nt_r_m"
            )
    else:
        p1, p2 = st.columns(2)
        with p1:
            entry_price = st.number_input(
                "Entry Price", value=None, placeholder="e.g., 19850.25", key="nt_entry"
            )
            stop_price = st.number_input(
                "Stop Price", value=None, placeholder="e.g., 19820.00", key="nt_stop"
            )
            tp_price = st.number_input(
                "Take Profit", value=None, placeholder="e.g., 19920.00", key="nt_tp"
            )
        with p2:
            exit_price = st.number_input(
                "Exit Price", value=None, placeholder="e.g., 19905.00", key="nt_exit"
            )
            position_size = st.number_input(
                "Position Size", value=None, placeholder="optional", key="nt_size"
            )
            risk_amount = st.number_input(
                "Risk ($)", value=None, placeholder="optional", key="nt_risk"
            )
        rc1, rc2 = st.columns(2)
        with rc1:
            result = st.selectbox(
                "Result", ["Win", "Loss", "Breakeven"], key="nt_result"
            )
        with rc2:
            pnl = st.number_input(
                "P&L ($)", value=None, placeholder="e.g., 250.00", key="nt_pnl"
            )

        # Live auto-R preview (read-only). Same formula as the trade service.
        if entry_price and stop_price and abs(entry_price - stop_price) > 0:
            risk_dist = abs(entry_price - stop_price)
            ar1, ar2 = st.columns(2)
            if tp_price:
                ar1.metric(
                    "Planned R", f"{abs(tp_price - entry_price) / risk_dist:.2f}R"
                )
            if exit_price:
                ar2.metric(
                    "Realized R", f"{abs(exit_price - entry_price) / risk_dist:.2f}R"
                )

# ── Step 5 — Psychology & Notes ───────────────────────────────────
with tabs[4]:
    mindset = st.text_area(
        "How were you feeling during this trade?",
        placeholder="e.g., Patient and disciplined — waited for my model.",
        key="nt_mindset",
    )
    emo_before = emo_during = emo_after = None
    with st.expander("Advanced emotion log (optional)"):
        e1, e2, e3 = st.columns(3)
        emo_before = e1.selectbox("Before", ["—"] + EMOTIONS, key="nt_emo_before")
        emo_during = e2.selectbox("During", ["—"] + EMOTIONS, key="nt_emo_during")
        emo_after = e3.selectbox("After", ["—"] + EMOTIONS, key="nt_emo_after")
    notes = st.text_area("Notes", height=120, key="nt_notes")

# ── Step 6 — Screenshot ───────────────────────────────────────────
with tabs[5]:
    st.markdown("#### Chart Screenshot")
    st.caption("Upload your chart screenshot for post-trade AI review.")
    screenshot_file = st.file_uploader(
        "Upload screenshot", type=["png", "jpg", "jpeg", "webp"], key="nt_shot"
    )
    if screenshot_file is not None:
        st.image(screenshot_file, caption="Preview", use_container_width=True)
    screenshot_url = st.text_input(
        "Or paste a direct image URL (optional)", key="nt_shot_url"
    )
    st.caption(
        "Must be a direct image link (.png, .jpg, .webp). "
        "TradingView public snapshot links work."
    )


# ── Assemble trade payload ────────────────────────────────────────
def _confluence_flag(name: str) -> int:
    return 1 if name in confluences else 0


def _build_trade_data() -> dict:
    final_during = (
        emo_during if emo_during and emo_during != "—" else (mindset.strip() or None)
    )
    mistakes = []
    if mistake_tag and mistake_tag != "None":
        mistakes.append(
            mistake_other.strip() if mistake_tag == "Other" else mistake_tag
        )

    return {
        "trade_date": str(trade_date),
        "entry_time": str(entry_time),  # hash-only; dropped by create_trade
        "killzone": killzone,
        "asset": (asset or "").strip(),
        "asset_class": asset_class,
        "session": session,
        "timeframe": timeframe,
        "direction": direction,
        "htf_bias": htf_bias.lower(),
        "bias": ltf_bias.lower(),
        "setup_type": setup_type,
        "confirmation_model": confirmation_model.strip() or None,
        "liquidity_sweep": _confluence_flag("Liquidity Sweep"),
        "fvg_used": _confluence_flag("FVG"),
        "order_block_used": _confluence_flag("Order Block"),
        "bos": _confluence_flag("BOS"),
        "choch": _confluence_flag("CHoCH"),
        "followed_rules": {"Yes": 1, "No": 0, "Partial": None}.get(followed_rules),
        "mistake_tags": json.dumps(mistakes),
        "entry_price": entry_price,
        "stop_price": stop_price,
        "tp_price": tp_price,
        "exit_price": exit_price,
        "position_size": position_size,
        "risk_amount": risk_amount,
        "rr_realized": manual_r if skip_prices else None,
        "result": result,
        "pnl": pnl,
        "emotions_before": emo_before if emo_before and emo_before != "—" else None,
        "emotions_during": final_during,
        "emotions_after": emo_after if emo_after and emo_after != "—" else None,
        "notes": notes.strip() or None,
        "user_id": current_user_id(),
    }


def _validate(data: dict) -> list:
    errors = []
    if not data["asset"]:
        errors.append("Asset is required.")
    if not mindset.strip():
        errors.append("Tell us how you were feeling (Psychology tab).")
    e, s = data["entry_price"], data["stop_price"]
    if e and s:
        if data["direction"] == "Long" and s >= e:
            errors.append("Long trade: stop price must be below entry price.")
        if data["direction"] == "Short" and s <= e:
            errors.append("Short trade: stop price must be above entry price.")
    return errors


def _persist(data: dict) -> None:
    trade = create_trade(data)
    if screenshot_file is not None:
        try:
            save_screenshot(trade.id, screenshot_file)
        except Exception as exc:  # noqa: BLE001 — screenshot is best-effort
            st.warning(f"Trade saved, but the screenshot upload failed: {exc}")
    if (screenshot_url or "").strip():
        try:
            save_screenshot_url(trade.id, screenshot_url.strip())
        except Exception:  # noqa: BLE001
            pass
    st.session_state["_nt_saved_id"] = trade.id


def _do_save(override: bool) -> None:
    # Step 1 guard: block a second save while one is in flight.
    if st.session_state.get("trade_submit_in_progress"):
        st.warning("Trade is already being saved. Please wait.")
        st.stop()

    data = _build_trade_data()
    errors = _validate(data)
    if errors:
        for err in errors:
            st.toast(err, icon="✕")
        return

    # Step 2 guard: hash-based recent-duplicate detection.
    if not override and find_recent_duplicate(data, user_id=current_user_id()):
        st.session_state["_nt_dup_pending"] = True
        st.rerun()

    st.session_state["trade_submit_in_progress"] = True
    try:
        _persist(data)
        st.session_state["trade_submit_in_progress"] = False
        st.session_state.pop("_nt_dup_pending", None)
        st.rerun()
    except Exception as exc:  # noqa: BLE001 — surface a clean error, reset the guard
        st.session_state["trade_submit_in_progress"] = False
        st.toast(f"Could not save trade: {exc}", icon="✕")


st.divider()

if st.session_state.get("_nt_saved_id"):
    st.markdown(
        '<div style="background:rgba(46,125,50,0.15);border:1px solid #2e7d32;'
        'border-radius:8px;padding:10px 14px;color:#7bd88f">'
        "✅ <strong>Trade saved successfully!</strong></div>",
        unsafe_allow_html=True,
    )
    if st.button("Log another trade", type="primary"):
        st.session_state.pop("_nt_saved_id", None)
        st.rerun()
    st.stop()

if st.button("Save Trade", type="primary", use_container_width=True):
    _do_save(override=False)

if st.session_state.get("_nt_dup_pending"):
    st.warning("A trade with identical details was just saved. Is this a duplicate?")
    d1, d2 = st.columns(2)
    if d1.button("Yes, skip it", use_container_width=True):
        st.session_state.pop("_nt_dup_pending", None)
        st.rerun()
    if d2.button("No, save it anyway", use_container_width=True):
        st.session_state.pop("_nt_dup_pending", None)
        _do_save(override=True)
