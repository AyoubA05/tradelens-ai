import sys
from pathlib import Path

# parents[4] of src/tradelens/ui/pages/1_NewTrade.py  →  project root
_root = str(Path(__file__).resolve().parents[4])
if _root not in sys.path:
    sys.path.insert(0, _root)

import datetime  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
from html import escape  # noqa: E402

import streamlit as st  # noqa: E402

from src.tradelens.services.app_settings import (  # noqa: E402
    DEFAULT_TIMEZONE,
    get_timezone,
)
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
from src.tradelens.services.trade_validation import (  # noqa: E402
    OutcomeMismatch,
    canonical_outcome,
)
from src.tradelens.ui.components.ai_autofill_review import (  # noqa: E402
    ai_sourced_fields,
    clear_autofill_state,
    drain_pending_writes,
    has_staged_detection,
    mark_field_edited,
    persist_analysis_for_trade,
    render_autofill_review,
)
from src.tradelens.ui.components.auth import current_user_id, require_auth  # noqa: E402
from src.tradelens.ui.components.demo_banner import render_demo_banner  # noqa: E402
from src.tradelens.ui.components.sidebar import render_sidebar  # noqa: E402
from src.tradelens.ui.components.theme import inject_css  # noqa: E402
from src.tradelens.ui.components.trade_wizard import (  # noqa: E402
    LAST_STEP,
    WIZARD_STEPS,
    current_step,
    draft_completion,
    keep_alive,
    missing_required_fields,
    next_step,
    previous_step,
    reset_wizard_state,
    set_step,
)
from src.tradelens.ui.components.ui import error_box  # noqa: E402
from src.tradelens.ui.components.workspace import (  # noqa: E402
    render_section_header,
    render_workspace_header,
)
from src.tradelens.ui.design_system import (  # noqa: E402
    inject_design_system,
    render_badge,
    render_banner,
    render_chip_row,
    render_step_indicator,
)
from src.tradelens.utils.format import humanize, parse_price  # noqa: E402

_log = logging.getLogger(__name__)


def _error_box(message: str) -> None:
    """Readable, non-crashing error block (shared ui.error_box builder)."""
    st.markdown(error_box(message), unsafe_allow_html=True)


st.set_page_config(page_title="Log completed trade")
inject_css()
inject_design_system()  # design_system.py wins ties (injected after theme)
require_auth()
uid = current_user_id()
render_demo_banner()
render_sidebar()

# Streamlit discards a widget's session state on any run where the widget is
# not rendered. This wizard renders one step at a time, so every value must
# be re-asserted before the first widget is created or the draft evaporates.
keep_alive(st.session_state)
STEP = current_step(st.session_state)
# Write it back: the first run would otherwise leave the key absent, so the
# step a trader is on would not survive a rerun triggered by anything else.
set_step(st.session_state, STEP)

st.markdown(
    render_workspace_header(
        "Log completed trade",
        "Five steps. Your draft is kept as you move between them.",
        eyebrow=f"Step {STEP} of {LAST_STEP} · {WIZARD_STEPS[STEP - 1]}",
    ),
    unsafe_allow_html=True,
)

# ── Options ───────────────────────────────────────────────────────
TIMEFRAMES = ["1m", "5m", "15m", "1H", "4H", "D"]
BIAS_OPTIONS = ["Bullish", "Bearish", "Consolidation"]
# Phase 4: named setup models (composed reads, not single components).
DEFAULT_SETUPS = [
    "Liquidity Sweep + FVG/IFVG",
    "BOS + FVG",
    "FVG + OB",
    "CHoCH Entry",
    "OB Retest",
    "Other",
]
# Phase 4 evidence list. "MSS/CHOCH" (not the spec's "CHoCH") is kept because
# it is the canonical AI-autofill confluence label (test-pinned) — a rename
# would leave AI-applied session values outside the widget's options.
CONFLUENCES = [
    "Liquidity Sweep",
    "BOS",
    "MSS/CHOCH",
    "FVG",
    "IFVG",
    "OB Retest",
    "S/R Rejection",
    "Candle Close",
    "VWAP",
    "No Confirmation",
]
DEFAULT_MISTAKES = [
    "Early Entry",
    "Late Entry",
    "FOMO",
    "Revenge Trading",
    "Moved Stop",
    "Closed Early",
    "Against Bias",
    "News Trade",
    "Overtrading",
    "Bad Stop Placement",
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


# ── Strategy Profile autofill (safe, non-trade-specific defaults) ──
_strategy = get_active_strategy(uid) if uid is not None else None
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
# Phase 4: mistakes are a multiselect (empty selection = clean trade).
MISTAKE_OPTIONS = _dedup([*_profile_mistakes, *DEFAULT_MISTAKES])

_entry_tf = _profile_tf.get("entry")
_tf_default = TIMEFRAMES.index(_entry_tf) if _entry_tf in TIMEFRAMES else 1

# Drain AI Autofill writes staged on the previous run BEFORE any form widget is
# instantiated (Streamlit forbids mutating a widget's state after it is created).
drain_pending_writes()

# ── Defaults, seeded once ─────────────────────────────────────────
# Seeded rather than passed as widget `value=`/`index=` so the readers below
# and the widgets themselves cannot disagree about what a blank draft holds.
# Fields whose empty state is genuinely "nothing entered" (prices, P&L, free
# text) are deliberately absent: None and "" are the honest defaults there.
for _key, _default in {
    "nt_date": datetime.date.today(),
    "nt_entry_time": "09:30",
    "nt_asset_select": ASSET_OPTIONS[0],
    "nt_timeframe": TIMEFRAMES[_tf_default],
    "nt_htf": BIAS_OPTIONS[0],
    "nt_ltf": BIAS_OPTIONS[0],
    "nt_setup": SETUP_OPTIONS[0],
    "nt_result": "Win",
    "nt_emo_before": "—",
    "nt_emo_during": "—",
    "nt_emo_after": "—",
}.items():
    st.session_state.setdefault(_key, _default)


# ── Every value, read from session state ──────────────────────────
# The wizard renders one step at a time, so the save payload cannot be built
# from widget return values — four of the five steps have not run. Session
# state is the single source of truth; the widgets below only edit it.
def _txt(key: str) -> str:
    return str(st.session_state.get(key) or "").strip()


def _raw(key: str) -> str:
    return str(st.session_state.get(key) or "")


def _seq(key: str) -> list:
    return list(st.session_state.get(key) or [])


trade_date = st.session_state.get("nt_date") or datetime.date.today()
entry_time_raw = _raw("nt_entry_time")
entry_time = parse_time_input(entry_time_raw)

has_settings_owner = isinstance(uid, int) and not isinstance(uid, bool) and uid > 0
user_tz = get_timezone(uid) if has_settings_owner else DEFAULT_TIMEZONE
# Session is auto-derived from the entry time — no manual session/killzone input.
session = detect_session(entry_time, trade_date, user_tz)
killzone = detect_killzone(entry_time, trade_date, user_tz)  # silent, for analytics

asset_choice = st.session_state.get("nt_asset_select") or ASSET_OPTIONS[0]
is_custom_asset = asset_choice == OTHER
asset = _txt("nt_asset_custom") if is_custom_asset else asset_choice
# Item 5: asset class is derived from the symbol, never asked.
asset_class = detect_asset_class(asset) or "Futures"
timeframe = st.session_state.get("nt_timeframe") or TIMEFRAMES[_tf_default]
htf_bias = st.session_state.get("nt_htf") or BIAS_OPTIONS[0]
ltf_bias = st.session_state.get("nt_ltf") or BIAS_OPTIONS[0]

setup_type = st.session_state.get("nt_setup") or SETUP_OPTIONS[0]
confluences = _seq("nt_confluences")
confirmation_model = _raw("nt_confirm")
followed_rules = st.session_state.get("nt_rules")
rule_broken = _raw("nt_rule_broken")
result = st.session_state.get("nt_result") or "Win"
pnl = st.session_state.get("nt_pnl")
risk_amount = st.session_state.get("nt_risk")
position_size = st.session_state.get("nt_size")
manual_r = st.session_state.get("nt_r")

entry_price_raw = _raw("nt_entry")
stop_price_raw = _raw("nt_stop")
tp_price_raw = _raw("nt_tp")
exit_price_raw = _raw("nt_exit")
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

process_notes = _raw("nt_process_notes")
mindset = _raw("nt_mindset")
did_well = _raw("nt_did_well")
do_better = _raw("nt_do_better")
mistake_tags_sel = _seq("nt_mistake_tags")
emo_before = st.session_state.get("nt_emo_before")
emo_during = st.session_state.get("nt_emo_during")
emo_after = st.session_state.get("nt_emo_after")

screenshot_file = st.session_state.get("nt_shot")
screenshot_url = _raw("nt_shot_url")

# Field view the wizard's pure rules read (its own vocabulary, not widget keys).
_FIELD_VALUES = {
    "screenshot": screenshot_file or screenshot_url,
    "asset": asset,
    "entry_time": entry_time,
    "timeframe": timeframe,
    "setup_type": setup_type,
    "confluences": confluences,
    "followed_rules": followed_rules,
    "result": result,
    "pnl": pnl,
    "risk_amount": risk_amount,
    "position_size": position_size,
    "process_notes": process_notes,
    "mindset": mindset,
    "did_well": did_well,
    "do_better": do_better,
}


# ══════════════════════════════════════════════════════════════════
# Step 1 — Screenshot & AI Autofill (screenshot-first; Bug 2 + Change A)
# ══════════════════════════════════════════════════════════════════
def _step_screenshot() -> None:
    st.markdown(render_section_header("Start with your chart"), unsafe_allow_html=True)
    st.caption(
        "Upload your TradingView screenshot. The AI reviews it automatically — "
        "you confirm before anything is applied."
    )
    st.markdown(
        render_banner(
            "Post-trade review only. AI observations are reflection, "
            "never live signals.",
            "info",
        ),
        unsafe_allow_html=True,
    )
    screenshot_file = st.file_uploader(
        "Upload screenshot", type=["png", "jpg", "jpeg", "webp"], key="nt_shot"
    )
    # The two-panel AI review shows the chart itself; only preview here when
    # no detection is staged (avoids rendering the same screenshot twice).
    if screenshot_file is not None and not has_staged_detection():
        st.image(screenshot_file, caption="Preview", width="stretch")
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
def _step_context() -> None:
    st.markdown(render_section_header("When and what"), unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        st.date_input("Trade date", key="nt_date")
    with c2:
        st.text_input(
            "Entry time",
            placeholder="e.g., 09:30 or 9:30 AM",
            key="nt_entry_time",
            on_change=mark_field_edited,
            args=("entry_time",),
        )
        if entry_time is None and entry_time_raw.strip():
            # Inline, next to the field that caused it.
            st.caption("Not a readable time — try 09:30 or 9:30 AM.")
    st.markdown(
        f"Session &nbsp;{render_badge(session, 'primary')}",
        unsafe_allow_html=True,
    )
    st.caption(f"Auto-detected from entry time · Timezone: {user_tz} (Settings)")

    st.divider()
    m1, m2 = st.columns(2)
    with m1:
        choice = st.selectbox(
            "Asset",
            ASSET_OPTIONS,
            key="nt_asset_select",
            on_change=mark_field_edited,
            args=("asset",),
        )
        if choice == OTHER:
            st.text_input(
                "Custom asset",
                placeholder="e.g., MNQ",
                key="nt_asset_custom",
                on_change=mark_field_edited,
                args=("asset",),
            )
    with m2:
        st.selectbox(
            "Timeframe",
            TIMEFRAMES,
            key="nt_timeframe",
            on_change=mark_field_edited,
            args=("timeframe",),
        )
        st.selectbox(
            "HTF bias",
            BIAS_OPTIONS,
            key="nt_htf",
            on_change=mark_field_edited,
            args=("htf_bias",),
        )
        st.selectbox(
            "LTF bias",
            BIAS_OPTIONS,
            key="nt_ltf",
            on_change=mark_field_edited,
            args=("ltf_bias",),
        )


# ══════════════════════════════════════════════════════════════════
# Step 3 — Trade Details (Setup + Risk & Outcome merged; Change C)
# ══════════════════════════════════════════════════════════════════
def _avoid_list_match(setup: str, avoided_raw: str) -> "str | None":
    """First avoid-list entry matching the chosen setup (case-insensitive,
    either-direction substring), or None."""
    setup_low = (setup or "").strip().lower()
    if not setup_low:
        return None
    for token in avoided_raw.split(","):
        tok = token.strip()
        tok_low = tok.lower()
        if tok_low and (tok_low in setup_low or setup_low in tok_low):
            return tok
    return None


def _step_execution() -> None:
    st.markdown(render_section_header("Setup and evidence"), unsafe_allow_html=True)
    st.selectbox("Setup model", SETUP_OPTIONS, key="nt_setup")

    _avoided_raw = ((_strategy or {}).get("setups_avoided") or "").strip()
    if _avoided_raw:
        _avoid_hit = _avoid_list_match(setup_type, _avoided_raw)
        if _avoid_hit:
            st.markdown(
                render_banner(
                    f"'{setup_type}' matches your avoid list ({_avoid_hit}). "
                    "Log it honestly — the review is where it pays off.",
                    "warning",
                ),
                unsafe_allow_html=True,
            )
        else:
            st.caption(f"Avoid per your profile: {_avoided_raw}")

    picked = st.multiselect(
        "Evidence",
        CONFLUENCES,
        key="nt_confluences",
        on_change=mark_field_edited,
        args=("confluences",),
    )
    if picked:
        st.markdown(render_chip_row(list(picked)), unsafe_allow_html=True)
    st.text_area(
        "What confirmed the trade?",
        placeholder="e.g., 1m IFVG + 5m BOS",
        key="nt_confirm",
        height=68,
        help="Optional.",
    )

    rules = st.radio(
        "Followed your rules?",
        ["Yes", "No", "Partial"],
        index=None,  # blank / "Not answered" by default
        horizontal=True,
        key="nt_rules",
    )
    if rules in ("No", "Partial"):
        st.text_input(
            "Which rule, or what went wrong?",
            key="nt_rule_broken",
        )
        st.caption("Tag the mistake itself in Reflection.")
    elif rules == "Yes":
        st.caption("Clean trade — no mistake tag needed.")

    st.divider()
    st.markdown(render_section_header("Risk and outcome"), unsafe_allow_html=True)
    if _strategy and (_strategy.get("risk_rules") or "").strip():
        st.caption(f"Risk plan: {_strategy['risk_rules']}")

    def _sync_result_from_pnl() -> None:
        """Typing a P&L selects the matching result.

        P&L is the fact, so it decides the label. Overriding the dropdown
        into a contradiction is blocked at save time by _validate().
        """
        v = st.session_state.get("nt_pnl")
        if v is None:
            return
        st.session_state["nt_result"] = (
            "Win" if v > 0 else ("Loss" if v < 0 else "Breakeven")
        )

    st.selectbox(
        "Result",
        ["Win", "Loss", "Breakeven"],
        key="nt_result",
        help="Derived from P&L when you enter one.",
    )

    # Change E — P&L and Risk in the same row, side by side.
    pr1, pr2 = st.columns(2)
    pr1.number_input(
        "P&L ($)",
        value=None,
        placeholder="e.g., 250.00",
        key="nt_pnl",
        on_change=_sync_result_from_pnl,
    )
    pr2.number_input("Risk ($)", value=None, placeholder="e.g., 125.00", key="nt_risk")

    o1, o2 = st.columns(2)
    # Change D — position size is a whole number only (integer, no decimals).
    o1.number_input(
        "Position size",
        value=None,
        min_value=0,
        step=1,
        format="%d",
        placeholder="e.g., 3",
        key="nt_size",
    )
    o2.number_input(
        "R multiple",
        value=None,
        placeholder="e.g., 2.0",
        key="nt_r",
        help="Optional — calculated from prices or P&L ÷ risk when left blank.",
    )

    # Item 7: prices are TEXT inputs parsed exactly — st.number_input rounds
    # typed values to its step/format precision (NG 3.3765 became 3.38).
    with st.expander("Exact price levels (markup)"):
        st.caption(
            "Optional. Exact prices give precise R and infer direction; the "
            "AI's detected levels from Screenshot land here. Decimals are kept "
            "exactly as typed (e.g. 3.3765)."
        )
        e1, e2 = st.columns(2)
        e1.text_input(
            "Entry price",
            placeholder="e.g., 19850.25",
            key="nt_entry",
            on_change=mark_field_edited,
            args=("entry_price",),
        )
        e1.text_input(
            "Stop price",
            placeholder="e.g., 3.3765",
            key="nt_stop",
            on_change=mark_field_edited,
            args=("stop_price",),
        )
        e2.text_input(
            "Take profit",
            placeholder="e.g., 19920.00",
            key="nt_tp",
            on_change=mark_field_edited,
            args=("tp_price",),
        )
        e2.text_input(
            "Exit price",
            placeholder="e.g., 19905.00",
            key="nt_exit",
            on_change=mark_field_edited,
            args=("exit_price",),
        )
        for _label, _raw_value, _parsed in _PRICE_INPUTS:
            if str(_raw_value or "").strip() and _parsed is None:
                st.caption(f"{_label} isn't a number.")

    st.markdown(_r_readout("Planned R", _planned_r()), unsafe_allow_html=True)
    st.markdown(_r_readout("Realized R", _derived_r()), unsafe_allow_html=True)


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


def _planned_r() -> "float | None":
    """Planned R from the marked-up levels: |entry−tp| / |entry−stop|."""
    if entry_price and stop_price and tp_price and abs(entry_price - stop_price) > 0:
        return round(abs(tp_price - entry_price) / abs(entry_price - stop_price), 2)
    return None


_FAINT = "color:var(--tl-text-faint)"


def _r_readout(label: str, value: "float | None") -> str:
    """Read-only mono R line; blank values render a faint 'Not entered yet'."""
    if value is None:
        return f"**{label}:** <span style='{_FAINT}'>Not entered yet</span>"
    return f"**{label}:** `{value:.2f}` <span style='{_FAINT}'>(calculated)</span>"


# ══════════════════════════════════════════════════════════════════
# Step 4 — Reflection (Change G — Notes field removed)
# ══════════════════════════════════════════════════════════════════
def _step_reflection() -> None:
    st.markdown(render_section_header("Reflection"), unsafe_allow_html=True)
    st.caption("Every field here is optional. Nothing on this step blocks saving.")
    # Item 8: mechanical process notes — what the chart did and what the trader
    # did, separate from emotional state. Feeds the per-trade AI review.
    st.text_area(
        "What happened during this trade?",
        placeholder=(
            "e.g., Price swept liquidity, broke structure, I moved to "
            "break-even after the 2nd IFVG break, then hit TP."
        ),
        key="nt_process_notes",
    )
    st.text_area(
        "How were you feeling?",
        placeholder="e.g., Patient and disciplined — waited for my model.",
        key="nt_mindset",
    )
    tags = st.multiselect("Tag any mistakes", MISTAKE_OPTIONS, key="nt_mistake_tags")
    if tags:
        st.markdown(
            render_chip_row(list(tags), {m: "danger" for m in tags}),
            unsafe_allow_html=True,
        )
    # Progressive disclosure: four equally weighted text areas made the step
    # look like a form to survive. The two that matter most stay open; the
    # longer-form pair and the emotion log open on demand.
    with st.expander("Longer notes — what went well, what to change"):
        st.text_area(
            "What did you do well?",
            placeholder="e.g., Waited for the sweep instead of front-running it.",
            key="nt_did_well",
        )
        st.text_area(
            "What should you do better next time?",
            placeholder="e.g., Leave the stop alone once it's set.",
            key="nt_do_better",
        )
    with st.expander("Emotion log — before / during / after"):
        ec1, ec2, ec3 = st.columns(3)
        ec1.selectbox("Before", ["—"] + EMOTIONS, key="nt_emo_before")
        ec2.selectbox("During", ["—"] + EMOTIONS, key="nt_emo_during")
        ec3.selectbox("After", ["—"] + EMOTIONS, key="nt_emo_after")


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
    # Phase 4: mistakes come from the Step-4 multiselect (empty = clean trade).
    mistakes = list(mistake_tags_sel)

    # Structured reflection lines share the existing notes column — the
    # rule-break description plus the Phase-4 did-well / do-better answers.
    note_lines = []
    if rule_broken.strip():
        note_lines.append(f"Rule broken: {rule_broken.strip()}")
    if did_well.strip():
        note_lines.append(f"Did well: {did_well.strip()}")
    if do_better.strip():
        note_lines.append(f"Do better next time: {do_better.strip()}")
    extra_notes = "\n".join(note_lines)

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
        "user_id": uid,
    }


def _validate(data: dict) -> list:
    """Hard, save-blocking errors only. Psychology/screenshot are recommendations."""
    errors = []
    if not data["asset"]:
        errors.append("Asset is required (Context).")
    if entry_time is None:
        errors.append("Enter time like 09:30 or 9:30 AM (Context).")
    e, s = data["entry_price"], data["stop_price"]
    if e is not None and s is not None and e == s:
        errors.append("Entry and stop price can't be equal (Execution).")
    for label, raw, parsed in _PRICE_INPUTS:
        if str(raw or "").strip() and parsed is None:
            errors.append(f"{label} isn't a number (Execution).")
    try:
        canonical_outcome(data.get("result"), data.get("pnl"))
    except (OutcomeMismatch, ValueError) as exc:
        errors.append(f"{exc} (Execution).")
    return errors


def _soft_warnings() -> list:
    """Recommended-but-optional gaps — shown, never blocking.

    Step names track the wizard: pointing a trader at "Psychology" when the
    step is called Reflection sends them looking for something that is not
    there.
    """
    w = []
    if not mindset.strip():
        w.append("Reflection — add how you felt (recommended).")
    if followed_rules is None:
        w.append("Execution — answer 'Followed your rules?' (recommended).")
    if not (screenshot_file is not None or (screenshot_url or "").strip()):
        w.append("Screenshot — not attached (optional).")
    return w


def _persist(data: dict) -> None:
    trade = create_trade(data)
    if screenshot_file is not None:
        try:
            save_screenshot(trade.id, screenshot_file)
        except Exception:  # noqa: BLE001 — screenshot is best-effort
            st.warning(
                "Trade saved. The screenshot didn't upload — "
                "add it later from the trade's page."
            )
    if (screenshot_url or "").strip():
        try:
            save_screenshot_url(trade.id, screenshot_url.strip())
        except Exception:  # noqa: BLE001
            pass
    # Persist any staged AI screenshot analysis to the now-saved trade so the
    # Journal shows it without paying for a second vision call.
    persist_analysis_for_trade(trade.id)
    st.session_state["just_saved_trade_id"] = trade.id


def _do_save(override: bool) -> None:
    if st.session_state.get("trade_submit_in_progress"):
        st.warning("This trade is already saving.")
        return

    data = _build_trade_data()
    errors = _validate(data)
    if errors:
        _error_box("Please fix before saving:\n" + "\n".join(f"• {e}" for e in errors))
        return

    if not override and find_recent_duplicate(data, user_id=uid):
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


_NOT_ENTERED = f"<span style='{_FAINT}'>Not entered yet</span>"
_MONO = "font-family:ui-monospace,SFMono-Regular,Menlo,monospace"


def _tv(value) -> str:
    """Ticket value: escaped text, faint 'Not entered yet' when blank."""
    if value is None or not str(value).strip() or str(value).strip() == "—":
        return _NOT_ENTERED
    return escape(str(value))


def _tv_mono(text: "str | None") -> str:
    return f"<span style='{_MONO}'>{escape(text)}</span>" if text else _NOT_ENTERED


def _tv_money(value) -> str:
    return _tv_mono(f"${value:,.2f}" if value is not None else None)


def _tv_note(text: str, max_len: int = 70) -> str:
    t = (text or "").strip()
    if not t:
        return _NOT_ENTERED
    return escape(t if len(t) <= max_len else t[:max_len].rstrip() + "…")


def _ticket_section(title: str, rows: list) -> tuple:
    """Render only the rows the trader actually filled in.

    Returns (html, blank_count). A review that lists every blank as "Not
    entered yet" announces incompleteness at the moment the trader is
    trying to finish; a section with nothing in it is dropped entirely.
    The blank counts are returned rather than printed so the caller can
    state completeness ONCE, instead of repeating a "left blank" row under
    every heading.
    """
    filled = [(label, value) for label, value in rows if value != _NOT_ENTERED]
    blanks = len(rows) - len(filled)
    if not filled:
        return "", blanks

    body = "".join(
        '<div style="display:flex;justify-content:space-between;gap:16px;'
        'padding:3px 0">'
        f'<span style="color:var(--tl-muted);font-size:12px;'
        f'text-transform:uppercase;letter-spacing:0.04em">{escape(label)}</span>'
        f'<span style="text-align:right">{value}</span></div>'
        for label, value in filled
    )
    return f"<h3>{escape(title)}</h3>{body}", blanks


def _ticket_html(data: dict) -> str:
    """Structured trade ticket for Review & Save (Phase 4, .tl-form-card)."""
    mistakes = json.loads(data["mistake_tags"] or "[]")
    fr = {1: "Yes", 0: "No"}.get(data["followed_rules"])

    market = [
        ("Date / Time", _tv(f"{data['trade_date']} {_time_str(entry_time)}")),
        (
            "Asset",
            (
                _tv(f"{data['asset']} ({data['asset_class']})")
                if data["asset"]
                else _NOT_ENTERED
            ),
        ),
        ("Session", _tv(data["session"])),
        ("Timeframe", _tv(data["timeframe"])),
        (
            "HTF / LTF Bias",
            _tv(f"{humanize(data['htf_bias'])} / {humanize(data['bias'])}"),
        ),
    ]
    if data["direction"]:  # only when inferred from exact prices
        market.append(("Direction (inferred)", _tv(data["direction"])))
    market.append(
        (
            "Screenshot",
            (
                "Attached"
                if (screenshot_file is not None or (screenshot_url or "").strip())
                else _NOT_ENTERED
            ),
        )
    )

    setup = [
        ("Setup Model", _tv(data["setup_type"])),
        ("Evidence", _tv(", ".join(confluences)) if confluences else _NOT_ENTERED),
        ("What confirmed it", _tv_note(data["confirmation_model"] or "")),
        ("Followed rules", _tv(fr)),
    ]

    risk_rows = [
        ("Result", _tv(data["result"])),
        ("P&L", _tv_money(data["pnl"])),
        ("Risk", _tv_money(data["risk_amount"])),
        (
            "Position size",
            _tv_mono(
                str(data["position_size"])
                if data["position_size"] is not None
                else None
            ),
        ),
        (
            "Planned R",
            _tv_mono(f"{_planned_r():.2f}" if _planned_r() is not None else None),
        ),
        (
            "Realized R",
            _tv_mono(f"{_derived_r():.2f}" if _derived_r() is not None else None),
        ),
    ]
    if data["entry_price"] and data["stop_price"]:
        risk_rows.append(
            (
                "Entry / Stop / TP / Exit",
                _tv_mono(
                    f"{data['entry_price']} / {data['stop_price']} / "
                    f"{data['tp_price'] or '—'} / {data['exit_price'] or '—'}"
                ),
            )
        )

    psych = [
        ("What happened", _tv_note(process_notes)),
        ("How you felt", _tv_note(mindset)),
        ("Did well", _tv_note(did_well)),
        ("Do better", _tv_note(do_better)),
        ("Mistakes tagged", _tv(", ".join(mistakes)) if mistakes else "None"),
    ]

    _ai_fields = ai_sourced_fields()
    _labels = [
        ("asset", "Asset"),
        ("timeframe", "Timeframe"),
        ("htf_bias", "HTF Bias"),
        ("ltf_bias", "LTF Bias"),
        ("confluences", "Evidence"),
        ("entry_price", "Entry"),
        ("stop_price", "Stop"),
        ("tp_price", "TP"),
        ("exit_price", "Exit"),
        ("entry_time", "Entry Time"),
    ]
    _names = ", ".join(label for key, label in _labels if key in _ai_fields)
    ai_rows = [
        (
            "AI suggested (still your call)",
            escape(_names) if _names else "None — manual entry",
        )
    ]

    rendered, blanks = [], 0
    for title, rows in (
        ("Market", market),
        ("Setup", setup),
        ("Risk & Outcome", risk_rows),
        ("Reflection", psych),
        ("AI Suggested", ai_rows),
    ):
        html, blank_count = _ticket_section(title, rows)
        rendered.append(html)
        blanks += blank_count

    # ONE completeness summary (spec 11.2), not a "left blank" row repeated
    # under every heading. It names what is recommended and still missing,
    # then counts the rest.
    missing = _soft_warnings()
    summary = []
    if missing:
        summary.extend(
            f'<div style="padding:3px 0;color:var(--tl-warning-ink)">{escape(m)}</div>'
            for m in missing
        )
    if blanks:
        summary.append(
            f'<div style="padding:3px 0;{_FAINT}">{blanks} other optional field'
            f'{"s" if blanks != 1 else ""} left blank. None of them block saving.'
            "</div>"
        )
    if summary:
        rendered.append(f"<h3>Completeness</h3>{''.join(summary)}")
    return f'<div class="tl-form-card">{"".join(rendered)}</div>'


# ══════════════════════════════════════════════════════════════════
# Step 5 — Review & Save
# ══════════════════════════════════════════════════════════════════
def _step_review() -> None:
    st.markdown(render_section_header("Review and save"), unsafe_allow_html=True)

    if st.session_state.get("just_saved_trade_id"):
        st.markdown(
            render_banner("Trade saved successfully.", "info"),
            unsafe_allow_html=True,
        )
        s1, s2, s3 = st.columns(3)
        s1.page_link("pages/2_Trades.py", label="View in Journal →")
        if s2.button("Log another trade", width="stretch"):
            st.session_state.pop("just_saved_trade_id", None)
            clear_autofill_state()  # fresh AI state for the next trade
            # Clears wizard-owned keys ONLY, and returns to step one. A reset
            # that took the session with it would sign the trader out at the
            # moment they finished their first trade.
            reset_wizard_state(st.session_state)
            st.rerun()
        s3.page_link("app.py", label="Go to Dashboard →")
        st.stop()

    _data = _build_trade_data()
    st.markdown(_ticket_html(_data), unsafe_allow_html=True)

    if st.session_state.get("_nt_dup_pending"):
        st.warning(
            "A trade with identical details was just saved. Is this a duplicate?"
        )
        d1, d2 = st.columns(2)
        if d1.button("Yes, skip it", width="stretch"):
            st.session_state.pop("_nt_dup_pending", None)
            st.rerun()
        if d2.button("No, save it anyway", width="stretch"):
            st.session_state.pop("_nt_dup_pending", None)
            _do_save(override=True)


# ══════════════════════════════════════════════════════════════════
# Render the active step, then the action bar
# ══════════════════════════════════════════════════════════════════
_STEP_BODIES = {
    1: _step_screenshot,
    2: _step_context,
    3: _step_execution,
    4: _step_reflection,
    5: _step_review,
}

# One progress system. Labels on desktop; the masthead eyebrow already
# carries "Step N of 5", which is what remains on a phone.
st.markdown(
    f'<div class="tl-wizard-progress">'
    f"{render_step_indicator(STEP, list(WIZARD_STEPS))}</div>",
    unsafe_allow_html=True,
)

# The container key changes with the step, so Streamlit mounts a new element
# and the CSS enter animation replays. That is the whole step transition.
with st.container(key=f"tl_step_{STEP}"):
    _STEP_BODIES[STEP]()


def _go_back() -> None:
    st.session_state.pop("_nt_step_errors", None)
    previous_step(st.session_state)


def _go_next() -> None:
    """Validate on attempted navigation — never on every keystroke."""
    missing = missing_required_fields(STEP, _FIELD_VALUES)
    if missing:
        st.session_state["_nt_step_errors"] = missing
        return
    st.session_state.pop("_nt_step_errors", None)
    next_step(st.session_state)


def _jump_to_context() -> None:
    st.session_state.pop("_nt_step_errors", None)
    set_step(st.session_state, 2)


_filled, _total = draft_completion(_FIELD_VALUES)
_blocking = _validate(_build_trade_data()) if STEP == LAST_STEP else []
_step_errors = st.session_state.get("_nt_step_errors") or []

with st.container(key="tl_wizard_bar"):
    if _step_errors:
        st.markdown(
            render_banner(
                "Needed before you continue: " + ", ".join(_step_errors) + ".",
                "warning",
            ),
            unsafe_allow_html=True,
        )
    if _blocking:
        _error_box("Fix before saving:\n" + "\n".join(f"• {e}" for e in _blocking))

    _back_col, _state_col, _next_col = st.columns([1, 2, 1.4])
    if STEP > 1:
        _back_col.button("← Back", key="secondary_nt_back", on_click=_go_back)
    # "Draft kept", not "Draft saved": next to a "Save completed trade"
    # button, "saved" reads as though the trade were already in the journal.
    _state_col.markdown(
        f'<p class="tl-wizard-draft">Draft kept · {_filled} of {_total} '
        f"fields filled</p>",
        unsafe_allow_html=True,
    )
    if STEP < LAST_STEP:
        _next_col.button(
            "Continue →", type="primary", width="stretch", on_click=_go_next
        )
    elif not st.session_state.get("_nt_dup_pending"):
        if _next_col.button(
            "Save completed trade",
            type="primary",
            width="stretch",
            disabled=bool(_blocking),
        ):
            _do_save(override=False)
        if _blocking:
            _next_col.button(
                "Go to Context", key="secondary_nt_fix", on_click=_jump_to_context
            )
