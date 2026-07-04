import sys
from pathlib import Path

# parents[4] of src/tradelens/ui/pages/1_NewTrade.py  →  project root
_root = str(Path(__file__).resolve().parents[4])
if _root not in sys.path:
    sys.path.insert(0, _root)

import datetime  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402

import streamlit as st  # noqa: E402

from src.tradelens.services.app_settings import get_timezone  # noqa: E402
from src.tradelens.services.assets import (  # noqa: E402
    OTHER,
    detect_asset_class,
    tradable_assets,
)
from src.tradelens.services.screenshot_service import (  # noqa: E402
    save_screenshot,
    save_screenshot_url,
)
from src.tradelens.services.sessions import (  # noqa: E402
    detect_killzone,
    detect_session,
    parse_time_input,
)
from src.tradelens.services.strategy import (  # noqa: E402
    get_active_strategy,
    parse_markets,
    parse_mistakes,
    parse_setups,
    parse_timeframes,
)
from src.tradelens.services.trade_service import (  # noqa: E402
    create_trade,
    find_recent_duplicate,
)
from src.tradelens.ui.components.ai_autofill_review import (  # noqa: E402
    ai_sourced_fields,
    clear_autofill_state,
    drain_pending_writes,
    mark_field_edited,
    persist_analysis_for_trade,
    render_autofill_review,
)
from src.tradelens.ui.components.auth import current_user_id, require_auth  # noqa: E402
from src.tradelens.ui.components.demo_banner import render_demo_banner  # noqa: E402
from src.tradelens.ui.components.sidebar import render_sidebar  # noqa: E402
from src.tradelens.ui.components.theme import inject_css  # noqa: E402
from src.tradelens.ui.components.ui import error_box, section_header  # noqa: E402
from src.tradelens.utils.format import humanize, parse_price  # noqa: E402

_log = logging.getLogger(__name__)


def _error_box(message: str) -> None:
    """Readable, non-crashing error block (shared ui.error_box builder)."""
    st.markdown(error_box(message), unsafe_allow_html=True)


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
TIMEFRAMES = ["1m", "5m", "15m", "1H", "4H", "D"]
BIAS_OPTIONS = ["Bullish", "Bearish", "Consolidation"]
DEFAULT_SETUPS = [
    "FVG",
    "Order Block",
    "BOS",
    "CHoCH",
    "Liquidity Sweep",
    "S/R Bounce",
    "Other",
]
CONFLUENCES = [
    "HTF Bias Aligned",
    "Liquidity Sweep",
    "FVG",
    "IFVG",
    "OB Retest",
    "BOS",
    "MSS/CHOCH",
    "VWAP",
    "Key Level",
    "News Avoided",
    "Killzone Timing",
]
DEFAULT_MISTAKES = [
    "FOMO Entry",
    "Late Entry",
    "Early Entry",
    "Bad SL Placement",
    "Moved Stop",
    "Closed Early",
    "Revenge Trade",
    "Overtrading",
    "Against Bias",
    "News Trade",
    "Outside Killzone",
    "No Confirmation",
]
EMOTIONS = ["Calm", "Confident", "Focused", "Anxious", "FOMO", "Revenge", "Neutral"]


def _dedup(seq):
    seen, out = set(), []
    for item in seq:
        key = str(item).lower()
        if item and key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _time_str(t) -> str:
    return t.strftime("%H:%M") if t else "—"


def _ratio_str(r) -> str:
    """Format an R multiple as a readable risk:reward ratio (Change F).

    2.0 → '2:1', 0.5 → '0.5:1', -1.0 → '-1:1'. None → '—'.
    """
    if r is None:
        return "—"
    try:
        return f"{float(r):g}:1"
    except (TypeError, ValueError):
        return "—"


# ── Strategy Profile autofill (safe, non-trade-specific defaults) ──
_strategy = get_active_strategy()
_profile_markets = parse_markets(_strategy)
_profile_setups = parse_setups(_strategy)
_profile_mistakes = parse_mistakes(_strategy)
_profile_tf = parse_timeframes(_strategy)
if _strategy:
    st.caption(f"Defaults from Strategy Profile: **{_strategy.get('name', '—')}**")

# Item 5: futures + forex only (plus the trader's own profile markets).
ASSET_OPTIONS = _dedup([*_profile_markets, *tradable_assets()]) + [OTHER]
ASSET_OPTIONS_CORE = [a for a in ASSET_OPTIONS if a != OTHER]
SETUP_OPTIONS = _dedup([*_profile_setups, *DEFAULT_SETUPS])
MISTAKE_OPTIONS = ["None"] + _dedup([*_profile_mistakes, *DEFAULT_MISTAKES]) + ["Other"]

_entry_tf = _profile_tf.get("entry")
_tf_default = TIMEFRAMES.index(_entry_tf) if _entry_tf in TIMEFRAMES else 1

# Drain AI Autofill writes staged on the previous run BEFORE any form widget is
# instantiated (Streamlit forbids mutating a widget's state after it is created).
drain_pending_writes()

# ── Tabs (steps) — screenshot-first; Save lives ONLY on Review & Save ─
tabs = st.tabs(
    [
        "1 · Screenshot & AI",
        "2 · Market Context",
        "3 · Trade Details",
        "4 · Psychology",
        "5 · Review & Save",
    ]
)

# ══════════════════════════════════════════════════════════════════
# Step 1 — Screenshot & AI Autofill (screenshot-first; Bug 2 + Change A)
# ══════════════════════════════════════════════════════════════════
with tabs[0]:
    st.markdown("#### Start here — add your chart")
    st.caption(
        "Upload your TradingView screenshot first. After you analyze it, the AI "
        "shows what it detected and you confirm before anything fills the form."
    )
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
    st.divider()
    render_autofill_review(
        screenshot_file=screenshot_file,
        screenshot_url=(screenshot_url or "").strip() or None,
        strategy_profile=_strategy,
        known_assets=ASSET_OPTIONS_CORE,
    )

# ══════════════════════════════════════════════════════════════════
# Step 2 — Market Context (Timing + Market Context merged; Change B)
# ══════════════════════════════════════════════════════════════════
with tabs[1]:
    st.markdown("#### Timing")
    c1, c2 = st.columns(2)
    with c1:
        trade_date = st.date_input("Trade Date", value=datetime.date.today())
    with c2:
        entry_time_raw = st.text_input(
            "Entry Time",
            value="09:30",
            placeholder="e.g., 09:30 or 9:30 AM",
            key="nt_entry_time",
            on_change=mark_field_edited,
            args=("entry_time",),
        )
    entry_time = parse_time_input(entry_time_raw)

    user_tz = get_timezone()
    # Session is auto-derived from the entry time — no manual session/killzone input.
    session = detect_session(entry_time, trade_date, user_tz)
    killzone = detect_killzone(entry_time, trade_date, user_tz)  # silent, for analytics
    st.text_input(
        "Market Session (auto-detected from entry time)",
        value=session,
        disabled=True,
    )
    st.caption(
        f"Switches automatically with your entry time · Timezone: **{user_tz}** (Settings)"
    )

    st.divider()
    st.markdown("#### Market Context")
    m1, m2 = st.columns(2)
    with m1:
        asset_choice = st.selectbox(
            "Asset",
            ASSET_OPTIONS,
            key="nt_asset_select",
            on_change=mark_field_edited,
            args=("asset",),
        )
        is_custom_asset = asset_choice == OTHER
        if is_custom_asset:
            asset = st.text_input(
                "Custom asset",
                placeholder="e.g., MNQ",
                key="nt_asset_custom",
                on_change=mark_field_edited,
                args=("asset",),
            )
        else:
            asset = asset_choice
        # Item 5: asset class is no longer a form input — it is derived from
        # the symbol (futures/forex scope; unknown customs default to Futures).
        asset_class = detect_asset_class(asset) or "Futures"
    with m2:
        timeframe = st.selectbox(
            "Timeframe",
            TIMEFRAMES,
            index=_tf_default,
            key="nt_timeframe",
            on_change=mark_field_edited,
            args=("timeframe",),
        )
        htf_bias = st.selectbox(
            "HTF Bias",
            BIAS_OPTIONS,
            key="nt_htf",
            on_change=mark_field_edited,
            args=("htf_bias",),
        )
        ltf_bias = st.selectbox(
            "LTF Bias",
            BIAS_OPTIONS,
            key="nt_ltf",
            on_change=mark_field_edited,
            args=("ltf_bias",),
        )

# ══════════════════════════════════════════════════════════════════
# Step 3 — Trade Details (Setup + Risk & Outcome merged; Change C)
# ══════════════════════════════════════════════════════════════════
with tabs[2]:
    st.markdown("#### Setup & Confirmation")
    setup_type = st.selectbox("Setup Type", SETUP_OPTIONS, key="nt_setup")
    confirmation_model = st.text_input(
        "Confirmation Model",
        placeholder="e.g., 1m IFVG + 5m BOS",
        key="nt_confirm",
    )
    confluences = st.multiselect(
        "Confluences",
        CONFLUENCES,
        key="nt_confluences",
        on_change=mark_field_edited,
        args=("confluences",),
    )
    if _strategy and (_strategy.get("setups_avoided") or "").strip():
        st.caption(f"⚠️ Avoid per your profile: {_strategy['setups_avoided']}")

    st.markdown("**Followed your rules?**")
    followed_rules = st.radio(
        "Followed your rules?",
        ["Yes", "No", "Partial"],
        index=None,  # blank / "Not answered" by default
        horizontal=True,
        label_visibility="collapsed",
        key="nt_rules",
    )

    mistake_tag = "None"
    mistake_other = ""
    rule_broken = ""
    if followed_rules in ("No", "Partial"):
        mistake_tag = st.selectbox("Mistake Tag", MISTAKE_OPTIONS, key="nt_mistake")
        if mistake_tag == "Other":
            mistake_other = st.text_input(
                "Describe the mistake", key="nt_mistake_other"
            )
        rule_broken = st.text_input(
            "What rule did you break or what mistake did you make?",
            key="nt_rule_broken",
        )
    elif followed_rules == "Yes":
        st.caption("Clean trade — no mistake tag needed.")

    st.divider()
    st.markdown("#### Risk & Outcome")
    if _strategy and (_strategy.get("risk_rules") or "").strip():
        st.caption(f"Risk plan: {_strategy['risk_rules']}")

    result = st.selectbox("Result", ["Win", "Loss", "Breakeven"], key="nt_result")

    # Change E — P&L and Risk in the same row, side by side.
    pr1, pr2 = st.columns(2)
    pnl = pr1.number_input(
        "P&L ($)", value=None, placeholder="e.g., 250.00", key="nt_pnl"
    )
    risk_amount = pr2.number_input(
        "Risk ($)", value=None, placeholder="e.g., 125.00", key="nt_risk"
    )

    o1, o2 = st.columns(2)
    # Change D — position size is a whole number only (integer, no decimals).
    position_size = o1.number_input(
        "Position size",
        value=None,
        min_value=0,
        step=1,
        format="%d",
        placeholder="e.g., 3",
        key="nt_size",
    )
    manual_r = o2.number_input(
        "R Multiple (optional)", value=None, placeholder="e.g., 2.0", key="nt_r"
    )

    # Item 7: prices are TEXT inputs parsed exactly — st.number_input rounds
    # typed values to its step/format precision (NG 3.3765 became 3.38).
    with st.expander("Exact price levels (markup) — optional"):
        st.caption(
            "Use exact prices for precise R, or apply the AI's detected markup "
            "prices from Step 1. Direction is inferred from entry vs. stop. "
            "Any decimal precision is kept exactly as typed (e.g. 3.3765)."
        )
        e1, e2 = st.columns(2)
        entry_price_raw = e1.text_input(
            "Entry Price",
            placeholder="e.g., 19850.25",
            key="nt_entry",
            on_change=mark_field_edited,
            args=("entry_price",),
        )
        stop_price_raw = e1.text_input(
            "Stop Price",
            placeholder="e.g., 3.3765",
            key="nt_stop",
            on_change=mark_field_edited,
            args=("stop_price",),
        )
        tp_price_raw = e2.text_input(
            "Take Profit",
            placeholder="e.g., 19920.00",
            key="nt_tp",
            on_change=mark_field_edited,
            args=("tp_price",),
        )
        exit_price_raw = e2.text_input(
            "Exit Price",
            placeholder="e.g., 19905.00",
            key="nt_exit",
            on_change=mark_field_edited,
            args=("exit_price",),
        )
    entry_price = parse_price(entry_price_raw)
    stop_price = parse_price(stop_price_raw)
    tp_price = parse_price(tp_price_raw)
    exit_price = parse_price(exit_price_raw)
    _PRICE_INPUTS = (
        ("Entry Price", entry_price_raw, entry_price),
        ("Stop Price", stop_price_raw, stop_price),
        ("Take Profit", tp_price_raw, tp_price),
        ("Exit Price", exit_price_raw, exit_price),
    )


def _derived_r() -> "float | None":
    """Best available R multiple: exact prices → manual R → P&L / risk (Change F)."""
    if entry_price and stop_price and exit_price and abs(entry_price - stop_price) > 0:
        risk_dist = abs(entry_price - stop_price)
        return round(abs(exit_price - entry_price) / risk_dist, 2)
    if manual_r is not None:
        return float(manual_r)
    if pnl is not None and risk_amount:
        try:
            return round(pnl / risk_amount, 2)
        except ZeroDivisionError:
            return None
    return None


# Change F — read-only T-Multiple (risk:reward) display, below P&L and Risk.
with tabs[2]:
    _r_now = _derived_r()
    st.markdown(
        f"**T-Multiple (R:R):** `{_ratio_str(_r_now)}` "
        "&nbsp;·&nbsp; <span style='opacity:0.7'>auto-derived from risk &amp; "
        "reward — read only</span>",
        unsafe_allow_html=True,
    )

# ══════════════════════════════════════════════════════════════════
# Step 4 — Psychology (Change G — Notes field removed)
# ══════════════════════════════════════════════════════════════════
with tabs[3]:
    mindset = st.text_area(
        "How were you feeling during this trade?",
        placeholder="e.g., Patient and disciplined — waited for my model.",
        key="nt_mindset",
    )
    # Item 8: mechanical process notes — what the chart did and what the trader
    # did, separate from emotional state. Feeds the per-trade AI review.
    process_notes = st.text_area(
        "What happened during this trade?",
        placeholder=(
            "e.g., Price swept liquidity, broke structure, I moved to "
            "break-even after the 2nd IFVG break, then hit TP."
        ),
        key="nt_process_notes",
    )
    emo_before = emo_during = emo_after = None
    with st.expander("Advanced emotion log (optional)"):
        ec1, ec2, ec3 = st.columns(3)
        emo_before = ec1.selectbox("Before", ["—"] + EMOTIONS, key="nt_emo_before")
        emo_during = ec2.selectbox("During", ["—"] + EMOTIONS, key="nt_emo_during")
        emo_after = ec3.selectbox("After", ["—"] + EMOTIONS, key="nt_emo_after")


# ── Assemble trade payload ────────────────────────────────────────
def _confluence_flag(name: str) -> int:
    return 1 if name in confluences else 0


def _infer_direction():
    """Infer direction from exact prices, else None (Direction is not asked)."""
    if entry_price is None or stop_price is None:
        return None
    if stop_price < entry_price:
        return "Long"
    if stop_price > entry_price:
        return "Short"
    return None


def _build_trade_data() -> dict:
    final_during = (
        emo_during if emo_during and emo_during != "—" else (mindset.strip() or None)
    )
    mistakes = []
    if mistake_tag and mistake_tag != "None":
        mistakes.append(
            mistake_other.strip() if mistake_tag == "Other" else mistake_tag
        )

    # Notes are no longer collected in Psychology (Change G); the only note we
    # keep is the rule-break description from the Setup section.
    extra_notes = ""
    if rule_broken.strip():
        extra_notes = f"Rule broken: {rule_broken.strip()}"

    size = int(position_size) if position_size is not None else None

    return {
        "trade_date": str(trade_date),
        # hash-only; dropped by create_trade. Normalized typed time.
        "entry_time": _time_str(entry_time) if entry_time else "",
        "killzone": killzone,
        "asset": (asset or "").strip(),
        "asset_class": asset_class,
        "session": session,
        "timeframe": timeframe,
        # Direction is inferred from exact prices only; otherwise left blank.
        "direction": _infer_direction(),
        "htf_bias": htf_bias.lower(),
        "bias": ltf_bias.lower(),
        "setup_type": setup_type,
        "strategy_used": (_strategy or {}).get("name"),
        "confirmation_model": confirmation_model.strip() or None,
        "liquidity_sweep": _confluence_flag("Liquidity Sweep"),
        "fvg_used": _confluence_flag("FVG"),
        "order_block_used": _confluence_flag("OB Retest"),
        "bos": _confluence_flag("BOS"),
        "choch": _confluence_flag("MSS/CHOCH"),
        "followed_rules": {"Yes": 1, "No": 0, "Partial": None}.get(followed_rules),
        "mistake_tags": json.dumps(mistakes),
        "entry_price": entry_price,
        "stop_price": stop_price,
        "tp_price": tp_price,
        "exit_price": exit_price,
        "position_size": size,
        "risk_amount": risk_amount,
        # create_trade recomputes rr_realized from prices when entry/stop/exit
        # are present; otherwise the manually entered R is kept.
        "rr_realized": manual_r,
        "result": result,
        "pnl": pnl,
        "emotions_before": emo_before if emo_before and emo_before != "—" else None,
        "emotions_during": final_during,
        "emotions_after": emo_after if emo_after and emo_after != "—" else None,
        "notes": extra_notes or None,
        "trade_process_notes": process_notes.strip() or None,
        "user_id": current_user_id(),
    }


def _validate(data: dict) -> list:
    """Hard, save-blocking errors only. Psychology/screenshot are recommendations."""
    errors = []
    if not data["asset"]:
        errors.append("Asset is required (Market Context).")
    if entry_time is None:
        errors.append("Enter time like 09:30 or 9:30 AM (Market Context).")
    e, s = data["entry_price"], data["stop_price"]
    if e is not None and s is not None and e == s:
        errors.append("Entry and stop price can't be equal (Trade Details).")
    for label, raw, parsed in _PRICE_INPUTS:
        if str(raw or "").strip() and parsed is None:
            errors.append(f"{label} isn't a number (Trade Details).")
    return errors


def _soft_warnings() -> list:
    """Recommended-but-optional gaps — shown, never blocking."""
    w = []
    if not mindset.strip():
        w.append("Psychology — add how you felt (recommended).")
    if followed_rules is None:
        w.append("Trade Details — answer 'Followed your rules?' (recommended).")
    if not (screenshot_file is not None or (screenshot_url or "").strip()):
        w.append("Screenshot — optional, not attached.")
    return w


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
    # Persist any staged AI screenshot analysis to the now-saved trade so the
    # Journal shows it without paying for a second vision call.
    persist_analysis_for_trade(trade.id)
    st.session_state["_nt_saved_id"] = trade.id


def _do_save(override: bool) -> None:
    if st.session_state.get("trade_submit_in_progress"):
        st.warning("Trade is already being saved. Please wait.")
        return

    data = _build_trade_data()
    errors = _validate(data)
    if errors:
        _error_box("Please fix before saving:\n" + "\n".join(f"• {e}" for e in errors))
        return

    if not override and find_recent_duplicate(data, user_id=current_user_id()):
        st.session_state["_nt_dup_pending"] = True
        st.rerun()

    st.session_state["trade_submit_in_progress"] = True
    try:
        _persist(data)
        st.session_state["trade_submit_in_progress"] = False
        st.session_state.pop("_nt_dup_pending", None)
        st.rerun()
    except Exception as exc:  # noqa: BLE001 — never crash the app on save
        st.session_state["trade_submit_in_progress"] = False
        _log.exception("Trade save failed")
        _error_box(
            "Could not save this trade. Please review your inputs and try again.\n"
            f"Details: {exc}"
        )


def _realized_r_str(data: dict) -> str:
    if data["entry_price"] and data["stop_price"] and data["exit_price"]:
        risk = abs(data["entry_price"] - data["stop_price"]) or None
        if risk:
            return f"{abs(data['exit_price'] - data['entry_price']) / risk:.2f}R"
    if data["rr_realized"] is not None:
        return f"{data['rr_realized']:.2f}R"
    return "—"


def _summary_rows(data: dict) -> list:
    pnl_str = f"${data['pnl']:,.2f}" if data["pnl"] is not None else "—"
    risk_str = (
        f"${data['risk_amount']:,.2f}" if data["risk_amount"] is not None else "—"
    )
    bias = f"{humanize(data['htf_bias'])} / {humanize(data['bias'])}"
    mistakes = json.loads(data["mistake_tags"] or "[]")
    fr = {1: "Yes", 0: "No", None: "—"}.get(data["followed_rules"])
    size_str = str(data["position_size"]) if data["position_size"] is not None else "—"

    # Outcome first — that's what traders care about.
    rows = [
        (
            "Result · P&L · Risk · R:R",
            f"{data['result']} · {pnl_str} · {risk_str} · {_ratio_str(data['rr_realized'])}",
        ),
        ("Date / Time", f"{data['trade_date']} {_time_str(entry_time)}"),
        ("Asset / Class", f"{data['asset'] or '—'} ({data['asset_class']})"),
        ("Market Session", data["session"]),
        ("Timeframe", data["timeframe"]),
        ("Position size", size_str),
        ("HTF / LTF Bias", bias),
        ("Setup", data["setup_type"]),
        ("Confirmation", data["confirmation_model"] or "—"),
        ("Followed rules", fr),
        ("Mistake", ", ".join(mistakes) if mistakes else "—"),
    ]
    if data["direction"]:  # only when inferred from exact prices
        rows.append(("Direction (inferred)", data["direction"]))
    if data["entry_price"] and data["stop_price"]:  # only when exact prices entered
        rows.append(
            (
                "Entry / Stop / TP / Exit",
                f"{data['entry_price'] or '—'} / {data['stop_price'] or '—'} / "
                f"{data['tp_price'] or '—'} / {data['exit_price'] or '—'}",
            )
        )
    rows.append(
        (
            "Screenshot",
            (
                "Attached"
                if (screenshot_file is not None or (screenshot_url or "").strip())
                else "Optional — not attached"
            ),
        )
    )
    return rows


# ══════════════════════════════════════════════════════════════════
# Step 5 — Review & Save
# ══════════════════════════════════════════════════════════════════
with tabs[4]:
    st.markdown("#### Review & Save")

    if st.session_state.get("_nt_saved_id"):
        st.markdown(
            '<div style="background:rgba(46,125,50,0.15);border:1px solid #2e7d32;'
            'border-radius:8px;padding:10px 14px;color:#7bd88f">'
            "✅ <strong>Trade saved successfully!</strong></div>",
            unsafe_allow_html=True,
        )
        if st.button("Log another trade", type="primary"):
            st.session_state.pop("_nt_saved_id", None)
            clear_autofill_state()  # fresh AI state for the next trade
            st.rerun()
        st.stop()

    _data = _build_trade_data()
    for label, value in _summary_rows(_data):
        st.markdown(f"**{label}:** {value}")

    # Surface which fields the AI suggested (still the trader's call to save).
    _ai_fields = ai_sourced_fields()
    if _ai_fields:
        _labels = [
            ("asset", "Asset"),
            ("timeframe", "Timeframe"),
            ("htf_bias", "HTF Bias"),
            ("ltf_bias", "LTF Bias"),
            ("confluences", "Confluences"),
            ("entry_price", "Entry"),
            ("stop_price", "Stop"),
            ("tp_price", "TP"),
            ("exit_price", "Exit"),
            ("entry_time", "Entry Time"),
        ]
        _names = ", ".join(label for key, label in _labels if key in _ai_fields)
        if _names:
            st.caption(f"🤖 AI-suggested (still your call to save): {_names}")

    _errors = _validate(_data)
    if _errors:
        _error_box("Fix before saving:\n" + "\n".join(f"• {e}" for e in _errors))
    _warnings = _soft_warnings()
    if _warnings:
        st.caption("Recommended (won't block save):")
        for _w in _warnings:
            st.caption(f"• {_w}")

    st.divider()
    if st.session_state.get("_nt_dup_pending"):
        st.warning(
            "A trade with identical details was just saved. Is this a duplicate?"
        )
        d1, d2 = st.columns(2)
        if d1.button("Yes, skip it", use_container_width=True):
            st.session_state.pop("_nt_dup_pending", None)
            st.rerun()
        if d2.button("No, save it anyway", use_container_width=True):
            st.session_state.pop("_nt_dup_pending", None)
            _do_save(override=True)
    elif st.button("Save Trade", type="primary", use_container_width=True):
        _do_save(override=False)
