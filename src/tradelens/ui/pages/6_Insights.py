"""
Insights & Review — Pattern Insights + the unified Weekly Recap (Item 10).

One destination for reflection: deterministic Pattern Insights (no AI call),
the unified Weekly Recap — ONE AI call that receives both the weekly trade data
and the deterministic pattern statistics and returns performance/process review
plus pattern signals — and the on-demand Daily Debrief. The recap auto-runs on
page load and a saved recap is reused instead of paying for a new call.
Failures surface a specific inline reason — never a generic "AI unavailable".

This is post-trade reflection only — never live signals, predictions, or advice.
"""

import sys
import datetime
from html import escape
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
    generate_insights,
)
from src.tradelens.services.strategy import (  # noqa: E402
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
from src.tradelens.ui.components.ui import error_box  # noqa: E402
from src.tradelens.ui.design_system import (  # noqa: E402
    get_asset_as_base64,
    inject_design_system,
    render_badge,
    render_banner,
    render_empty_state,
    render_kpi_card,
    render_section_header,
)
from src.tradelens.utils.ai_utils import is_ai_enabled  # noqa: E402

st.set_page_config(page_title="Insights & Review", layout="wide")
inject_css()
inject_design_system()  # design_system.py wins ties (injected after theme)
require_auth()
render_demo_banner()
render_sidebar()
st.markdown(
    render_section_header(
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

if df.empty:
    st.markdown(
        render_empty_state(
            "",
            "No trades yet",
            "Log a few trades and the AI will start reviewing your journal.",
        ),
        unsafe_allow_html=True,
    )
    # page_link needs the multipage registry, which standalone AppTest boots
    # don't build — degrade to a plain slug link (sidebar pattern).
    try:
        st.page_link("pages/1_NewTrade.py", label="Log a trade →")
    except Exception:  # noqa: BLE001 — registry-less boots/tests only
        st.markdown(
            '<a href="/NewTrade" target="_self">Log a trade →</a>',
            unsafe_allow_html=True,
        )
    st.stop()


# ══════════════════════════════════════════════════════════════════
# PATTERN INSIGHTS  (deterministic, always on — no AI call)
# ══════════════════════════════════════════════════════════════════
# Item 10: the former separate AI pattern-cards section (which made its own
# second AI call) is retired — pattern signals now come from the single Weekly
# Recap call below, which receives the weekly stats AND the pattern statistics.
st.markdown(render_section_header("Pattern Insights"), unsafe_allow_html=True)
st.caption("Reflection only — these describe what already happened in your journal.")
st.markdown(
    render_banner("Reflective insights only, not trade signals.", "info"),
    unsafe_allow_html=True,
)

if len(df) < 5:
    st.info(f"Log 5+ trades for richer pattern insights. Current: {len(df)} trades.")

# Insight-type → card variant / marker glyph (geometric shapes, not emoji).
_VARIANT_BY_TYPE = {"positive": "strength", "negative": "leak", "neutral": "neutral"}
_ICON_BY_VARIANT = {"strength": "▲", "leak": "▼", "neutral": "◆"}
_CONF_LABEL = {"low": "Low", "medium": "Medium", "high": "High"}


def _insight_card_html(ins: dict, sample_n: int) -> str:
    """tl-insight-card with a CATEGORICAL confidence badge top-right.

    The deterministic pattern engine reports confidence as low/medium/high —
    design_system.render_insight_card would render a percentage, which implies
    a precision the engine doesn't have, so the card is composed here from the
    same CSS classes with render_badge(confidence-<tier>) instead.
    """
    variant = _VARIANT_BY_TYPE.get(str(ins.get("type")), "neutral")
    icon = _ICON_BY_VARIANT[variant]
    level = str(ins.get("confidence", "low"))
    if level not in _CONF_LABEL:
        level = "low"
    badge = render_badge(f"{_CONF_LABEL[level]} confidence", f"confidence-{level}")
    title = escape(str(ins.get("title", "")))
    body = escape(str(ins.get("body", "")))
    return (
        f'<div class="tl-insight-card {variant}">'
        '<div class="tl-insight-head">'
        f'<span class="tl-insight-icon">{icon}</span>'
        f'<span class="tl-insight-title">{title}</span>'
        f"{badge}</div>"
        f'<p class="tl-insight-body">{body}</p>'
        '<p class="tl-insight-evidence">'
        f"Evidence: based on {sample_n} journaled trades</p>"
        "</div>"
    )


det_insights = generate_insights(df, _strategy)
if det_insights:
    dcols = st.columns(2)
    for i, ins in enumerate(det_insights):
        dcols[i % 2].markdown(
            _insight_card_html(ins, len(df)), unsafe_allow_html=True
        )


# ══════════════════════════════════════════════════════════════════
# WEEKLY RECAP  (one AI call: review + pattern signals; auto-run; cached)
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


# Performance snapshot backdrop: recap_bg.png + rgba overlay (hero pattern).
_recap_b64 = get_asset_as_base64("recap_bg.png")
_RECAP_STYLE = (
    "background-image: linear-gradient(rgba(13,15,17,0.72), "
    f"rgba(13,15,17,0.72)), url(data:image/png;base64,{_recap_b64});"
    if _recap_b64
    else ""
)


def _render_week_stats(stats: dict) -> None:
    """KPI snapshot row above the AI text (recap_bg + overlay wrapper)."""
    if not stats:
        return
    pf = stats.get("profit_factor")
    if not stats.get("trades"):
        pf_val = None  # nothing traded — N/A, not ∞
    elif pf is None:
        pf_val = float("inf")  # no losing trades this week
    else:
        pf_val = pf
    cards = "".join(
        [
            render_kpi_card("Trades", stats.get("trades", 0), format="number"),
            render_kpi_card(
                "Win Rate", (stats.get("win_rate") or 0.0) * 100, format="percent"
            ),
            render_kpi_card("Net P&L", stats.get("total_pnl", 0.0)),
            render_kpi_card("Profit Factor", pf_val, format="ratio"),
            # Sign preserved by the service: negative = rule-breaking cost money.
            render_kpi_card("Edge Leak", stats.get("total_edge_leak", 0.0)),
        ]
    )
    st.markdown(
        f'<div class="tl-hero-wrap" style="{_RECAP_STYLE}">'
        f'<div class="tl-kpi-row">{cards}</div></div>',
        unsafe_allow_html=True,
    )


def _render_review_body(review: dict) -> None:
    # Render the COMPLETE markdown once — never st.write() on a generator and
    # never render partial chunks mid-stream (character-by-character bug).
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
    with st.spinner("Writing this week's recap…"):
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
st.markdown(render_section_header("Weekly Recap"), unsafe_allow_html=True)
st.caption(
    "One unified recap of a completed week — performance, what worked, pattern "
    "signals, and rule adherence. Reflection only, never signals or advice."
)

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
st.markdown(render_section_header("Daily Debrief"), unsafe_allow_html=True)
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
