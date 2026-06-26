import sys
import math
import datetime
from pathlib import Path
from typing import Optional

# parents[4] of src/tradelens/ui/pages/*.py  →  project root
_root = str(Path(__file__).resolve().parents[4])
if _root not in sys.path:
    sys.path.insert(0, _root)

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src.tradelens.services.metrics_store import get_computed_at  # noqa: E402
from src.tradelens.services.trade_service import get_trades  # noqa: E402
from src.tradelens.services.metrics import (  # noqa: E402
    by_day_of_week,
    by_setup_type,
    by_strategy,
    compute_basic_metrics,
    compute_expectancy,
    compute_profit_factor_raw,
    confirmation_model_performance,
    consistency_score,
    drawdown_series,
    emotion_vs_rr,
    equity_curve_series,
    killzone_performance,
    mistake_frequency,
    r_multiple_distribution,
    total_edge_leak,
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
from src.tradelens.utils.ai_utils import is_ai_enabled  # noqa: E402
from src.tradelens.utils.format import humanize  # noqa: E402
from src.tradelens.services.weekly import (  # noqa: E402
    WeeklyReviewError,
    generate_weekly_review,
    get_weekly_review,
    get_weekly_reviews,
    save_weekly_review,
    week_bounds,
)
from src.tradelens.ui.components.auth import (  # noqa: E402
    current_user_id,
    require_auth,
)
from src.tradelens.ui.components.charts import (  # noqa: E402
    drawdown_chart,
    emotion_vs_rr_chart,
    equity_curve_chart,
    pnl_by_strategy_chart,
    profit_factor_gauge,
    r_multiple_histogram,
    setup_breakdown_chart,
    win_rate_by_dow_chart,
)
from src.tradelens.ui.components.calendar_view import render_calendar  # noqa: E402
from src.tradelens.ui.components.demo_banner import render_demo_banner  # noqa: E402
from src.tradelens.ui.components.sidebar import render_sidebar  # noqa: E402
from src.tradelens.ui.components.theme import inject_css  # noqa: E402
from src.tradelens.ui.components.ui import (  # noqa: E402
    empty_state,
    section_header,
)

st.set_page_config(page_title="Analytics", layout="wide")
inject_css()
require_auth()
render_demo_banner()
render_sidebar()
st.markdown(section_header("Analytics"), unsafe_allow_html=True)

_active_strategy = get_active_strategy()
if _active_strategy:
    st.caption(f"Strategy: {_active_strategy.get('name', '—')}")
else:
    st.warning(
        "⚠️ No active strategy profile. Add one in Strategy Profile to make AI "
        "reviews strategy-aware."
    )


def _fmt_pf(v: float) -> str:
    return "∞" if isinstance(v, float) and math.isinf(v) else f"{v:.2f}"


def _fmt_ts(ts: str) -> str:
    """Format ISO timestamp as 'Jun 10, 2026 at 11:28 PM'. Falls back to raw string."""
    try:
        dt = datetime.datetime.fromisoformat(ts)
        time_part = dt.strftime("%I:%M %p")
        if time_part.startswith("0"):
            time_part = time_part[1:]
        return f"{dt.strftime('%b')} {dt.day}, {dt.strftime('%Y')} at {time_part}"
    except Exception:
        return ts


@st.cache_data(ttl=60)
def _cached_computed_at(user_id: int = 1) -> Optional[str]:
    return get_computed_at(user_id=user_id)


@st.cache_data(ttl=60)
def _load_df(start: str, end: str, user_id=None) -> pd.DataFrame:
    trades = get_trades(start_date=start, end_date=end, user_id=user_id)
    return pd.DataFrame(
        [
            {
                "id": t.id,
                "trade_date": t.trade_date,
                "day_of_week": t.day_of_week,
                "session": t.session,
                "asset": t.asset,
                "timeframe": t.timeframe,
                "strategy_used": t.strategy_used,
                "setup_type": t.setup_type,
                "emotions_before": t.emotions_before,
                "rr_realized": t.rr_realized,
                "pnl": t.pnl,
                "result": t.result,
                "killzone": t.killzone,
                "confirmation_model": t.confirmation_model,
                "mistake_tags": t.mistake_tags,
                "htf_bias": t.htf_bias,
                "followed_rules": t.followed_rules,
                "ai_grade": t.ai_grade,
                "user_grade": t.user_grade,
            }
            for t in trades
        ]
    )


@st.cache_data(ttl=60)
def _load_all_df(user_id=None) -> pd.DataFrame:
    """All trades (no date filter) — powers the Calendar tab."""
    return _load_df("0000-01-01", "9999-12-31", user_id)


# ── Tabs ──────────────────────────────────────────────────────────
tab_perf, tab_cal, tab_weekly, tab_insights = st.tabs(
    ["Performance", "Calendar", "Weekly Review", "Pattern Insights"]
)


# ══════════════════════════════════════════════════════════════════
# PERFORMANCE
# ══════════════════════════════════════════════════════════════════
def _render_performance() -> None:
    fcol1, fcol2 = st.columns([1, 1])
    today = datetime.date.today()
    with fcol1:
        start_date = st.date_input(
            "From", value=today - datetime.timedelta(days=90), key="an_from"
        )
    with fcol2:
        end_date = st.date_input("To", value=today, key="an_to")

    df_raw = _load_df(str(start_date), str(end_date), current_user_id())

    # DEMO_MODE on a cold/empty DB: show rich synthetic data so analytics is alive.
    if df_raw.empty and is_demo():
        df_raw = get_demo_df()

    if df_raw.empty:
        st.markdown(
            empty_state(
                "No trades in this range yet — log a trade to unlock your analytics.",
                cta_label="Log a trade",
                cta_href="/NewTrade",
            ),
            unsafe_allow_html=True,
        )
        return

    # --- Filters built from loaded data ---
    fc1, fc2, fc3 = st.columns(3)
    all_assets = sorted(df_raw["asset"].dropna().unique().tolist())
    all_sessions = sorted(df_raw["session"].dropna().unique().tolist())
    all_strategies = sorted(df_raw["strategy_used"].dropna().unique().tolist())
    with fc1:
        selected_assets = st.multiselect("Asset", options=all_assets, key="an_asset")
    with fc2:
        selected_sessions = st.multiselect(
            "Session", options=all_sessions, key="an_session"
        )
    with fc3:
        selected_strategies = st.multiselect(
            "Strategy", options=all_strategies, key="an_strat"
        )

    df = df_raw.copy()
    if selected_assets:
        df = df[df["asset"].isin(selected_assets)]
    if selected_sessions:
        df = df[df["session"].isin(selected_sessions)]
    if selected_strategies:
        df = df[df["strategy_used"].isin(selected_strategies)]

    if df.empty:
        st.warning(
            "No trades match the selected filters. Try adjusting the date range "
            "or filters."
        )
        return

    # --- Compute metrics (all delegated to metrics.py — no math here) ---
    m = compute_basic_metrics(df)
    pf = compute_profit_factor_raw(df)
    exp = compute_expectancy(m)
    eq_df = equity_curve_series(df)
    dd_df = drawdown_series(df)
    rr_df = r_multiple_distribution(df)

    rr_values = (
        df["rr_realized"].dropna()
        if "rr_realized" in df.columns
        else pd.Series(dtype=float)
    )
    median_rr = float(rr_values.median()) if not rr_values.empty else None

    dow_df = by_day_of_week(df)
    strat_df = by_strategy(df)
    setup_df = by_setup_type(df)
    emo_df = emotion_vs_rr(df)

    # --- KPI row ---
    pf_display = _fmt_pf(pf)
    avg_rr = m.get("avg_rr_realized", 0.0)
    cs = consistency_score(df)
    cs_display = f"{cs:.0f}/100" if cs else "—"
    # consistency_score returns 0 below 5 trades — say so instead of a bare dash.
    cs_help = (
        "Process score (0–100): rule adherence, mistake cleanliness, grade trend."
        if cs
        else "Log 5+ trades to calculate consistency."
    )

    k1, k2, k3, k4, k5, k6, k7 = st.columns(7)
    k1.metric("Total P/L", f"${m['total_pnl']:,.2f}")
    k2.metric("Win Rate", f"{m['win_rate']:.1%}")
    k3.metric("Profit Factor", pf_display)
    k4.metric("Expectancy", f"${exp:,.2f}")
    k5.metric("Avg R Realized", f"{avg_rr:.2f}R")
    k6.metric("Total Trades", m["total_trades"])
    k7.metric("Consistency", cs_display, help=cs_help)

    last_ts = _cached_computed_at()
    if last_ts:
        st.caption(f"Last refreshed: {_fmt_ts(last_ts)}")

    st.divider()

    # --- Row 1: Equity curve | Drawdown ---
    r1c1, r1c2 = st.columns(2)
    with r1c1:
        st.subheader("Equity Curve")
        st.plotly_chart(
            equity_curve_chart(eq_df), use_container_width=True, key="an_equity"
        )
        if eq_df.empty:
            st.caption("No trades in this period to plot.")
    with r1c2:
        st.subheader("Drawdown")
        st.plotly_chart(
            drawdown_chart(dd_df), use_container_width=True, key="an_drawdown"
        )
        if dd_df.empty:
            st.caption("No drawdown data available.")

    # --- Row 2: Win rate by DOW | P/L by strategy ---
    r2c1, r2c2 = st.columns(2)
    with r2c1:
        st.subheader("Win Rate by Day of Week")
        st.plotly_chart(
            win_rate_by_dow_chart(dow_df), use_container_width=True, key="an_dow"
        )
        if dow_df.empty:
            st.caption("Log more trades to see day-of-week trends.")
    with r2c2:
        st.subheader("P/L by Strategy")
        st.plotly_chart(
            pnl_by_strategy_chart(strat_df), use_container_width=True, key="an_strategy"
        )
        if strat_df.empty:
            st.caption("Assign strategies to trades to see this breakdown.")

    # --- Row 3: Profit factor gauge | R-multiple histogram ---
    r3c1, r3c2 = st.columns(2)
    with r3c1:
        st.subheader("Profit Factor")
        st.plotly_chart(profit_factor_gauge(pf), use_container_width=True, key="an_pf")
    with r3c2:
        st.subheader("R-Multiple Distribution")
        st.plotly_chart(
            r_multiple_histogram(rr_df, median_rr=median_rr),
            use_container_width=True,
            key="an_rr",
        )
        if rr_df.empty:
            st.caption("Log trades with R-multiple to see distribution.")

    # --- Bonus row: Emotion vs R | Setup breakdown ---
    b1, b2 = st.columns(2)
    with b1:
        st.subheader("Emotion vs. R-Multiple")
        st.plotly_chart(
            emotion_vs_rr_chart(emo_df), use_container_width=True, key="an_emo"
        )
        if emo_df.empty:
            st.caption("Add emotion labels to trades to see this chart.")
    with b2:
        st.subheader("Setup Breakdown")
        st.plotly_chart(
            setup_breakdown_chart(setup_df), use_container_width=True, key="an_setup"
        )
        if setup_df.empty:
            st.caption("Assign setup types to trades to see this chart.")

    # --- Killzone Performance ---
    st.divider()
    st.subheader("Killzone Performance")
    kz_df = killzone_performance(df)
    if kz_df.empty:
        st.caption(
            "No killzone data yet. Tag trades with a killzone to see this breakdown."
        )
    else:
        kc1, kc2 = st.columns([3, 2])
        with kc1:
            st.bar_chart(kz_df.set_index("killzone")["total_pnl"], height=300)
        with kc2:
            kz_disp = kz_df.copy()
            kz_disp["killzone"] = kz_disp["killzone"].map(humanize)
            kz_disp["win_rate"] = (kz_disp["win_rate"] * 100).round(1).astype(str) + "%"
            kz_disp["avg_rr_realized"] = kz_disp["avg_rr_realized"].round(2)
            kz_disp["profit_factor"] = kz_disp["profit_factor"].apply(_fmt_pf)
            kz_disp["total_pnl"] = kz_disp["total_pnl"].round(2)
            st.dataframe(
                kz_disp[
                    [
                        "killzone",
                        "trades",
                        "win_rate",
                        "avg_rr_realized",
                        "profit_factor",
                        "total_pnl",
                    ]
                ],
                hide_index=True,
                use_container_width=True,
            )

    # --- Confirmation model + mistake frequency ---
    cm_col, mk_col = st.columns(2)
    with cm_col:
        st.subheader("By Confirmation Model")
        cm_df = confirmation_model_performance(df)
        if cm_df.empty:
            st.caption("Tag trades with a confirmation model to see this breakdown.")
        else:
            cm_disp = cm_df.copy()
            cm_disp["win_rate"] = (cm_disp["win_rate"] * 100).round(1).astype(str) + "%"
            cm_disp["profit_factor"] = cm_disp["profit_factor"].apply(_fmt_pf)
            cm_disp["total_pnl"] = cm_disp["total_pnl"].round(2)
            st.dataframe(
                cm_disp[
                    [
                        "confirmation_model",
                        "trades",
                        "win_rate",
                        "profit_factor",
                        "total_pnl",
                    ]
                ],
                hide_index=True,
                use_container_width=True,
            )
    with mk_col:
        st.subheader("Mistake Frequency")
        mk_df = mistake_frequency(df)
        if mk_df.empty:
            st.caption("No mistake tags logged yet.")
        else:
            st.bar_chart(mk_df.set_index("mistake_tag")["count"], height=240)
            mk_disp = mk_df.copy()
            mk_disp["total_pnl"] = mk_disp["total_pnl"].round(2)
            mk_disp["avg_pnl"] = mk_disp["avg_pnl"].round(2)
            st.dataframe(mk_disp, hide_index=True, use_container_width=True)

    # --- Total Edge Leak ---
    st.divider()
    leak = total_edge_leak(df)
    lc1, lc2 = st.columns([1, 3])
    with lc1:
        st.metric(
            "Total Edge Leak",
            f"${leak:,.2f}",
            help="Net P&L of trades where you broke your rules or logged a mistake tag.",
        )
    with lc2:
        if leak < 0:
            st.caption(
                "The cumulative cost of rule-breaks and tagged mistakes. "
                "Tightening discipline here is your clearest edge."
            )
        elif leak > 0:
            st.caption(
                "Rule-break trades happened to net positive — lucky, not repeatable. "
                "Discipline keeps it that way."
            )
        else:
            st.caption("No rule-break or mistake-tagged trades in this period.")

    # Pattern Insights now live in their own auto-loading tab (see _render_insights).


# ══════════════════════════════════════════════════════════════════
# CALENDAR
# ══════════════════════════════════════════════════════════════════
def _render_calendar() -> None:
    df = _load_all_df(current_user_id())
    if df.empty and is_demo():
        df = get_demo_df()

    if df.empty:
        st.markdown(
            empty_state(
                "No trades yet — log a trade to see your calendar fill in.",
                cta_label="Log a trade",
                cta_href="/NewTrade",
            ),
            unsafe_allow_html=True,
        )
        return

    render_calendar(df)


# ══════════════════════════════════════════════════════════════════
# WEEKLY REVIEW
# ══════════════════════════════════════════════════════════════════
def _render_week_stats(stats: dict) -> None:
    if not stats:
        st.caption("Generate a review to see this week's stats.")
        return
    s1, s2, s3, s4, s5 = st.columns(5)
    s1.metric("Trades", stats.get("trades", 0))
    s2.metric("Win Rate", f"{stats.get('win_rate', 0.0):.1%}")
    s3.metric("Net P/L", f"${stats.get('total_pnl', 0.0):,.2f}")
    pf = stats.get("profit_factor")
    s4.metric("Profit Factor", "∞" if pf is None else f"{pf:.2f}")
    s5.metric("Edge Leak", f"${stats.get('total_edge_leak', 0.0):,.2f}")


def _render_review(review: dict) -> None:
    if review.get("content_md"):
        st.markdown(review["content_md"])
    thinking = review.get("thinking_summary")
    if thinking:
        with st.expander("How the AI reasoned"):
            st.markdown(thinking)
    cost = review.get("cost_usd")
    if cost:
        st.caption(f"Generation cost: ${cost:.4f}")


def _render_weekly() -> None:
    st.caption("Post-trade reflection on a completed week — not signals or advice.")
    today = datetime.date.today()
    picked = st.date_input(
        "Pick any day in the week to review", value=today, key="wk_pick"
    )
    monday, sunday = week_bounds(picked)
    st.subheader(f"Week of {monday} → {sunday}")

    uid = current_user_id()
    existing = get_weekly_review(monday, uid)
    _render_week_stats(existing["stats"] if existing else {})

    confirm_key = "wk_confirm_overwrite"
    if existing is None:
        # AI button only appears when a key is configured; stats above always show.
        if is_ai_enabled() and st.button(
            "Generate weekly review", type="primary", key="wk_gen"
        ):
            with st.spinner("Writing weekly review…"):
                try:
                    review, _usage = generate_weekly_review(monday)
                    if review["empty"]:
                        st.markdown(
                            empty_state(
                                "This week has no trades to review yet.",
                                cta_label="Log a trade",
                                cta_href="/NewTrade",
                            ),
                            unsafe_allow_html=True,
                        )
                    else:
                        save_weekly_review(review, overwrite=False, user_id=uid)
                        st.toast("Weekly review generated", icon="✅")
                        st.rerun()
                except WeeklyReviewError as exc:
                    st.toast(f"Could not generate review: {exc}", icon="❌")
                except Exception as exc:
                    st.toast(f"Unexpected error: {exc}", icon="❌")
    else:
        _render_review(existing)
        if (existing.get("stats") or {}).get("trades", 0) < 3:
            st.caption(
                "Based on a small sample. Log more trades for stronger insights."
            )
        st.divider()
        if st.session_state.get(confirm_key) == monday:
            st.warning(
                "Regenerating overwrites the saved review for this week and makes a "
                "new AI call. Continue?"
            )
            c1, c2 = st.columns(2)
            if c1.button("Confirm regenerate", type="primary", key="wk_confirm"):
                st.session_state.pop(confirm_key, None)
                with st.spinner("Regenerating…"):
                    try:
                        review, _usage = generate_weekly_review(monday)
                        if review["empty"]:
                            st.markdown(
                                empty_state("This week has no trades anymore."),
                                unsafe_allow_html=True,
                            )
                        else:
                            save_weekly_review(review, overwrite=True, user_id=uid)
                            st.toast("Weekly review regenerated", icon="✅")
                            st.rerun()
                    except WeeklyReviewError as exc:
                        st.toast(f"Could not regenerate review: {exc}", icon="❌")
                    except Exception as exc:
                        st.toast(f"Unexpected error: {exc}", icon="❌")
            if c2.button("Cancel", key="wk_cancel"):
                st.session_state.pop(confirm_key, None)
                st.rerun()
        else:
            if is_ai_enabled() and st.button("Regenerate review", key="wk_regen"):
                st.session_state[confirm_key] = monday
                st.rerun()

    st.divider()
    st.subheader("Past Reviews")
    history = get_weekly_reviews(uid)
    if not history:
        st.caption("No saved reviews yet.")
    else:
        for row in history:
            stats = row.get("stats") or {}
            label = (
                f"Week of {row['week_start']} · "
                f"P/L ${stats.get('total_pnl', 0.0):,.2f} · "
                f"Win {stats.get('win_rate', 0.0):.0%}"
            )
            with st.expander(label):
                _render_review(row)


def _render_insights() -> None:
    st.subheader("Pattern Insights")
    st.caption(
        "Reflection only — these describe what already happened in your journal. "
        "Not signals, predictions, or trade advice."
    )

    df = _load_all_df(current_user_id())
    if df.empty and is_demo():
        df = get_demo_df()

    if df.empty or len(df) < 5:
        count = 0 if df.empty else len(df)
        st.info(
            f"Log 5+ trades to start seeing pattern insights. Current: {count} trades."
        )
        return

    if st.button("Refresh insights", key="insights_refresh"):
        st.rerun()

    icons = {"positive": "🟢", "negative": "🔴", "neutral": "⚪"}
    conf_labels = {"low": "Low", "medium": "Medium", "high": "High"}
    for ins in generate_insights(df, get_active_strategy()):
        with st.container(border=True):
            st.markdown(f"{icons.get(ins['type'], '⚪')} **{ins['title']}**")
            st.markdown(ins["body"])
            st.caption(f"{conf_labels.get(ins['confidence'], 'Low')} confidence")

    # Optional deeper AI patterns (single AI call) — gated on the key.
    st.divider()
    st.markdown("**Deeper AI patterns** (optional)")
    if not is_ai_enabled():
        st.info(
            "🤖 Enable your ANTHROPIC_API_KEY in Settings for AI-generated "
            "pattern cards."
        )
    if st.button("Detect deeper patterns with AI", disabled=not is_ai_enabled()):
        with st.spinner("Detecting patterns…"):
            try:
                cards, _usage = detect_patterns(df)
                st.session_state["pattern_cards"] = cards
                st.session_state.pop("pattern_error", None)
            except Exception as exc:  # noqa: BLE001 — surface a clean message
                st.session_state["pattern_cards"] = None
                st.session_state["pattern_error"] = str(exc)

    if st.session_state.get("pattern_error"):
        st.warning(f"Could not generate patterns: {st.session_state['pattern_error']}")
    elif st.session_state.get("pattern_cards"):
        for _i, card in enumerate(st.session_state["pattern_cards"]):
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
                    if st.button("Add to Strategy Profile", key=f"add_rule_{_i}"):
                        append_insight(rule)
                        st.toast("Added to your Strategy Profile", icon="✅")


with tab_perf:
    _render_performance()

with tab_cal:
    _render_calendar()

with tab_weekly:
    _render_weekly()

with tab_insights:
    _render_insights()
