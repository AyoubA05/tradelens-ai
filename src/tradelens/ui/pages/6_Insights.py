"""
Insights & Review (Session F) — Pattern Insights + Weekly Review on one page.

Merges the two former Analytics tabs into a single destination where Claude runs
automatically on page load (no button to click): deeper AI pattern cards and the
weekly AI review are generated in the background and cached in session_state so
they do not re-run on every widget interaction. A saved weekly review is reused
instead of paying for a new call. Failures surface a specific inline reason —
never a generic "AI unavailable".

This is post-trade reflection only — never live signals, predictions, or advice.
"""

import sys
import datetime
from pathlib import Path

# parents[4] of src/tradelens/ui/pages/*.py  →  project root
_root = str(Path(__file__).resolve().parents[4])
if _root not in sys.path:
    sys.path.insert(0, _root)

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src.tradelens.services.debrief import (  # noqa: E402
    DebriefError,
    generate_debrief,
)
from src.tradelens.services.demo import get_demo_df, is_demo  # noqa: E402
from src.tradelens.services.patterns import (  # noqa: E402
    detect_patterns,
    generate_insights,
)
from src.tradelens.services.strategy import (  # noqa: E402
    append_insight,
    get_active_strategy,
)
from src.tradelens.services.trade_service import get_trades  # noqa: E402
from src.tradelens.services.weekly import (  # noqa: E402
    WeeklyReviewError,
    generate_weekly_review,
    get_weekly_review,
    save_weekly_review,
    week_bounds,
)
from src.tradelens.ui.components.auth import current_user_id, require_auth  # noqa: E402
from src.tradelens.ui.components.demo_banner import render_demo_banner  # noqa: E402
from src.tradelens.ui.components.sidebar import render_sidebar  # noqa: E402
from src.tradelens.ui.components.theme import inject_css  # noqa: E402
from src.tradelens.ui.components.ui import (  # noqa: E402
    empty_state,
    error_box,
    section_header,
)
from src.tradelens.utils.ai_utils import is_ai_enabled  # noqa: E402

st.set_page_config(page_title="Insights & Review", layout="wide")
inject_css()
require_auth()
render_demo_banner()
render_sidebar()
st.markdown(
    section_header(
        "Insights & Review",
        "AI reviews your journal automatically — patterns and a weekly review, "
        "reflection only, never signals or advice.",
    ),
    unsafe_allow_html=True,
)


def _error_box(message: str) -> None:
    """Readable, persistent inline error block (shared ui.error_box builder).

    Used instead of a transient st.toast so a failed AI call surfaces a specific,
    lasting reason the user can read and act on (Part 3 requirement).
    """
    st.markdown(error_box(message), unsafe_allow_html=True)


_DF_COLS = [
    "id",
    "trade_date",
    "day_of_week",
    "session",
    "asset",
    "setup_type",
    "rr_realized",
    "pnl",
    "result",
    "killzone",
    "confirmation_model",
    "mistake_tags",
    "htf_bias",
    "direction",
    "followed_rules",
]


def _load_df() -> pd.DataFrame:
    trades = get_trades(user_id=current_user_id())
    df = pd.DataFrame([{c: getattr(t, c, None) for c in _DF_COLS} for t in trades])
    if df.empty:
        return df
    return df[df["trade_date"].notna() & (df["trade_date"] != "")].reset_index(
        drop=True
    )


df = _load_df()
if df.empty and is_demo():
    df = get_demo_df()

_strategy = get_active_strategy()
_ai_on = is_ai_enabled() or is_demo()

# Invalidate cached AI output when the underlying data changes (cheap signature),
# so widget interactions never re-run the AI but new trades do.
_sig = (current_user_id(), int(len(df)))
if st.session_state.get("_ins_sig") != _sig:
    st.session_state["_ins_sig"] = _sig
    for k in ("_ins_cards", "_ins_cards_err"):
        st.session_state.pop(k, None)

if df.empty:
    st.markdown(
        empty_state(
            "No trades yet — log a few and the AI will start reviewing your journal.",
            cta_label="Log a trade",
            cta_href="/NewTrade",
        ),
        unsafe_allow_html=True,
    )
    st.stop()


# ══════════════════════════════════════════════════════════════════
# PATTERN INSIGHTS  (deterministic always; AI cards auto-run + cached)
# ══════════════════════════════════════════════════════════════════
def _auto_run_pattern_cards() -> None:
    """Run AI pattern detection once per data-signature, caching the result."""
    if not _ai_on:
        return
    if "_ins_cards" in st.session_state or "_ins_cards_err" in st.session_state:
        return
    with st.spinner("Analyzing your trading patterns with AI…"):
        try:
            cards, usage = detect_patterns(df)
            st.session_state["_ins_cards"] = cards
            # Cost telemetry: pattern cards have no persistence row of their
            # own, so log the call (best-effort) for the Settings dashboard.
            from src.tradelens.services.cost import log_ai_usage

            log_ai_usage("Pattern Detection", usage, user_id=current_user_id())
        except Exception as exc:  # noqa: BLE001 — surface a specific reason inline
            st.session_state["_ins_cards_err"] = str(exc)


def _render_pattern_cards() -> None:
    if not _ai_on:
        st.info(
            "Add your Anthropic API key in Settings to auto-generate AI pattern "
            "cards. The deterministic insights above always work without a key."
        )
        return
    err = st.session_state.get("_ins_cards_err")
    if err:
        _error_box(f"AI pattern detection couldn't run: {err}")
        if st.button("Retry pattern detection", key="ins_retry_cards"):
            st.session_state.pop("_ins_cards_err", None)
            st.rerun()
        return
    cards = st.session_state.get("_ins_cards") or []
    if not cards:
        st.caption("No additional AI patterns surfaced for this sample.")
        return
    for i, card in enumerate(cards):
        with st.container(border=True):
            st.markdown(f"**{card.get('insight', '—')}**")
            if card.get("evidence_stat"):
                st.markdown(f"**Evidence:** {card['evidence_stat']}")
            st.caption(
                f"Impact: {card.get('impact', '—')} · "
                f"Sample: {card.get('sample_size', '—')} trades · "
                f"Confidence: {card.get('confidence', '—')}"
            )
            rule = card.get("suggested_rule", "")
            if rule:
                st.markdown(f"*Suggested rule:* {rule}")
                if st.button("Add to Strategy Profile", key=f"ins_add_rule_{i}"):
                    append_insight(rule)
                    st.toast("Added to your Strategy Profile", icon="✅")


st.markdown(section_header("Pattern Insights"), unsafe_allow_html=True)
st.caption("Reflection only — these describe what already happened in your journal.")

if len(df) < 5:
    st.info(f"Log 5+ trades for richer pattern insights. Current: {len(df)} trades.")

icons = {"positive": "🟢", "negative": "🔴", "neutral": "⚪"}
conf_labels = {"low": "Low", "medium": "Medium", "high": "High"}
det_insights = generate_insights(df, _strategy)
if det_insights:
    dcols = st.columns(2)
    for i, ins in enumerate(det_insights):
        with dcols[i % 2]:
            with st.container(border=True):
                st.markdown(f"{icons.get(ins['type'], '⚪')} **{ins['title']}**")
                st.markdown(ins["body"])
                st.caption(f"{conf_labels.get(ins['confidence'], 'Low')} confidence")

st.markdown("**Deeper AI patterns**")
_auto_run_pattern_cards()
_render_pattern_cards()


# ══════════════════════════════════════════════════════════════════
# WEEKLY REVIEW  (auto-run for the most recent week with trades; cached)
# ══════════════════════════════════════════════════════════════════
def _default_week(frame: pd.DataFrame) -> datetime.date:
    """Week of the latest trade, so the page opens on a week worth reviewing."""
    try:
        latest = pd.to_datetime(frame["trade_date"], errors="coerce").max()
        if pd.notna(latest):
            return latest.date()
    except Exception:  # noqa: BLE001
        pass
    return datetime.date.today()


def _render_week_stats(stats: dict) -> None:
    if not stats:
        return
    s1, s2, s3, s4, s5 = st.columns(5)
    s1.metric("Trades", stats.get("trades", 0))
    s2.metric("Win Rate", f"{stats.get('win_rate', 0.0):.1%}")
    s3.metric("Net P/L", f"${stats.get('total_pnl', 0.0):,.2f}")
    pf = stats.get("profit_factor")
    s4.metric("Profit Factor", "∞" if pf is None else f"{pf:.2f}")
    s5.metric("Edge Leak", f"${stats.get('total_edge_leak', 0.0):,.2f}")


def _render_review_body(review: dict) -> None:
    if review.get("content_md"):
        st.markdown(review["content_md"])
    thinking = review.get("thinking_summary")
    if thinking:
        with st.expander("How the AI reasoned"):
            st.markdown(thinking)
    cost = review.get("cost_usd")
    if cost:
        st.caption(f"Generation cost: ${cost:.4f}")


def _auto_run_weekly(monday: str, uid) -> None:
    """Reuse a saved review if present; otherwise auto-generate + persist once."""
    err_key = f"_wk_err_{monday}"
    if st.session_state.get(err_key):
        return
    if get_weekly_review(monday, uid) is not None:
        return  # already saved — reuse, no API call
    if not _ai_on:
        return
    with st.spinner("Writing this week's AI review…"):
        try:
            review, _usage = generate_weekly_review(
                monday, user_id=uid, strategy_profile=_strategy
            )
            if not review["empty"]:
                save_weekly_review(review, overwrite=False, user_id=uid)
        except WeeklyReviewError as exc:
            st.session_state[err_key] = str(exc)
        except Exception as exc:  # noqa: BLE001 — specific inline reason, no crash
            st.session_state[err_key] = str(exc)


st.divider()
st.markdown(section_header("Weekly Review"), unsafe_allow_html=True)
st.caption("Post-trade reflection on a completed week — not signals or advice.")

uid = current_user_id()
picked = st.date_input(
    "Pick any day in the week to review", value=_default_week(df), key="ins_wk_pick"
)
monday, sunday = week_bounds(picked)
st.subheader(f"Week of {monday} → {sunday}")

_auto_run_weekly(monday, uid)
existing = get_weekly_review(monday, uid)
_render_week_stats(existing["stats"] if existing else {})

_wk_err = st.session_state.get(f"_wk_err_{monday}")
if existing is not None:
    _render_review_body(existing)
    if (existing.get("stats") or {}).get("trades", 0) < 3:
        st.caption("Based on a small sample. Log more trades for stronger insights.")
    if _ai_on and st.button("Regenerate this week", key="ins_wk_regen"):
        with st.spinner("Regenerating with AI…"):
            try:
                review, _usage = generate_weekly_review(
                    monday, user_id=uid, strategy_profile=_strategy
                )
                if review["empty"]:
                    st.caption("This week has nothing logged to review.")
                else:
                    save_weekly_review(review, overwrite=True, user_id=uid)
                    st.session_state.pop(f"_wk_err_{monday}", None)
                    st.rerun()
            except (WeeklyReviewError, Exception) as exc:  # noqa: BLE001
                _error_box(f"Could not regenerate: {exc}")
elif _wk_err:
    _error_box(f"AI weekly review couldn't run: {_wk_err}")
    if st.button("Retry weekly review", key="ins_wk_retry"):
        st.session_state.pop(f"_wk_err_{monday}", None)
        st.rerun()
else:
    st.caption("This week has nothing logged to review yet.")


# ══════════════════════════════════════════════════════════════════
# DAILY DEBRIEF  (on-demand coach review of one completed trading day)
# ══════════════════════════════════════════════════════════════════
def _latest_trade_date(frame: pd.DataFrame) -> datetime.date:
    """Most recent trading day in the journal — the day worth debriefing."""
    try:
        latest = pd.to_datetime(frame["trade_date"], errors="coerce").max()
        if pd.notna(latest):
            return latest.date()
    except Exception:  # noqa: BLE001
        pass
    return datetime.date.today()


def _run_daily_debrief(day_iso: str, day_trades: list, cache_key: str) -> None:
    with st.spinner("Writing your daily debrief…"):
        try:
            review, usage = generate_debrief(
                day_trades,
                strategy_profile=_strategy,
                period_label=f"Trading day {day_iso}",
            )
            st.session_state[cache_key] = review
            from src.tradelens.services.cost import log_ai_usage

            log_ai_usage("Daily Debrief", usage, user_id=uid)
        except DebriefError as exc:
            st.session_state[cache_key + "_err"] = str(exc)
        except Exception as exc:  # noqa: BLE001 — specific inline reason, no crash
            st.session_state[cache_key + "_err"] = str(exc)


st.divider()
st.markdown(section_header("Daily Debrief"), unsafe_allow_html=True)
st.caption(
    "A coach-like review of one completed trading day — reflection only, "
    "never signals or advice."
)

_dbf_day = st.date_input(
    "Trading day to review", value=_latest_trade_date(df), key="ins_dbf_day"
)
_dbf_iso = _dbf_day.isoformat()
_dbf_key = f"_dbf_{uid}_{_dbf_iso}"
_dbf_trades = get_trades(start_date=_dbf_iso, end_date=_dbf_iso, user_id=uid)

if not _dbf_trades:
    st.caption("No trades logged on this day — pick a day you traded.")
elif not _ai_on:
    st.info(
        "Add your Anthropic API key in Settings to generate a daily debrief. "
        "Your trades for the day are still listed in the Journal."
    )
else:
    _dbf_err = st.session_state.get(_dbf_key + "_err")
    _dbf_review = st.session_state.get(_dbf_key)
    if _dbf_review is not None:
        _render_week_stats(_dbf_review.get("stats") or {})
        _render_review_body(_dbf_review)
        if st.button("Regenerate debrief", key="ins_dbf_regen"):
            st.session_state.pop(_dbf_key, None)
            st.session_state.pop(_dbf_key + "_err", None)
            _run_daily_debrief(_dbf_iso, _dbf_trades, _dbf_key)
            st.rerun()
    elif _dbf_err:
        _error_box(f"Daily debrief couldn't run: {_dbf_err}")
        if st.button("Retry debrief", key="ins_dbf_retry"):
            st.session_state.pop(_dbf_key + "_err", None)
            st.rerun()
    else:
        n = len(_dbf_trades)
        plural = "s" if n != 1 else ""
        if st.button(
            f"Generate debrief for {_dbf_iso} ({n} trade{plural})",
            type="primary",
            key="ins_dbf_run",
        ):
            _run_daily_debrief(_dbf_iso, _dbf_trades, _dbf_key)
            st.rerun()
