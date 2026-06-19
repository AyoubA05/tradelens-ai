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
    compute_max_drawdown,
    compute_profit_factor_raw,
    confirmation_model_performance,
    drawdown_series,
    emotion_vs_rr,
    equity_curve_series,
    killzone_performance,
    mistake_frequency,
    r_multiple_distribution,
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

st.set_page_config(page_title="Analytics", page_icon="📊", layout="wide")

st.title("📊 Analytics")

# --- Sidebar: date range (loaded before trades so the date range drives the query) ---
with st.sidebar:
    st.header("Filters")
    today = datetime.date.today()
    start_date = st.date_input("From", value=today - datetime.timedelta(days=90))
    end_date = st.date_input("To", value=today)


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


# --- Cache the last-refreshed timestamp (avoids DB round-trip on every rerun) ---
@st.cache_data(ttl=60)
def _cached_computed_at(user_id: int = 1) -> Optional[str]:
    return get_computed_at(user_id=user_id)


# --- Load + cache trades for the selected date range ---
@st.cache_data(ttl=60)
def _load_df(start: str, end: str) -> pd.DataFrame:
    trades = get_trades(start_date=start, end_date=end)
    return pd.DataFrame([
        {
            "trade_date":      t.trade_date,
            "day_of_week":     t.day_of_week,
            "session":         t.session,
            "asset":           t.asset,
            "timeframe":       t.timeframe,
            "strategy_used":   t.strategy_used,
            "setup_type":      t.setup_type,
            "emotions_before": t.emotions_before,
            "rr_realized":     t.rr_realized,
            "pnl":             t.pnl,
            "result":          t.result,
            "killzone":           t.killzone,
            "confirmation_model": t.confirmation_model,
            "mistake_tags":       t.mistake_tags,
        }
        for t in trades
    ])


df_raw = _load_df(str(start_date), str(end_date))

# --- Empty state: no trades logged at all ---
if df_raw.empty:
    st.info("You haven't logged any trades yet. Head to New Trade to get started.")
    st.stop()

# --- Sidebar: multiselect filters built from loaded data ---
with st.sidebar:
    all_assets = sorted(df_raw["asset"].dropna().unique().tolist())
    all_sessions = sorted(df_raw["session"].dropna().unique().tolist())
    all_strategies = sorted(df_raw["strategy_used"].dropna().unique().tolist())

    selected_assets = st.multiselect("Asset", options=all_assets)
    selected_sessions = st.multiselect("Session", options=all_sessions)
    selected_strategies = st.multiselect("Strategy", options=all_strategies)

# --- Apply multiselect filters in pandas (service only supports single values) ---
df = df_raw.copy()
if selected_assets:
    df = df[df["asset"].isin(selected_assets)]
if selected_sessions:
    df = df[df["session"].isin(selected_sessions)]
if selected_strategies:
    df = df[df["strategy_used"].isin(selected_strategies)]

# --- Empty state: filters narrowed to nothing ---
if df.empty:
    st.warning("No trades match the selected filters. Try adjusting the date range or filters above.")
    st.stop()

# --- Compute metrics (all delegated to metrics.py — no math here) ---
m = compute_basic_metrics(df)
pf = compute_profit_factor_raw(df)
exp = compute_expectancy(m)
eq_df = equity_curve_series(df)
dd_df = drawdown_series(df)
max_dd = compute_max_drawdown(eq_df)
rr_df = r_multiple_distribution(df)

rr_values = df["rr_realized"].dropna() if "rr_realized" in df.columns else pd.Series(dtype=float)
median_rr = float(rr_values.median()) if not rr_values.empty else None

dow_df = by_day_of_week(df)
strat_df = by_strategy(df)
setup_df = by_setup_type(df)
emo_df = emotion_vs_rr(df)

# --- KPI row ---
pf_display = "∞" if math.isinf(pf) else f"{pf:.2f}"
avg_rr = m.get("avg_rr_realized", 0.0)

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Total P/L", f"${m['total_pnl']:,.2f}")
k2.metric("Win Rate", f"{m['win_rate']:.1%}")
k3.metric("Profit Factor", pf_display)
k4.metric("Expectancy", f"${exp:,.2f}")
k5.metric("Avg R Realized", f"{avg_rr:.2f}R")
k6.metric("Total Trades", m["total_trades"])

last_ts = _cached_computed_at()
if last_ts:
    st.caption(f"Last refreshed: {_fmt_ts(last_ts)}")

st.markdown("---")

# --- Row 1: Equity curve | Drawdown ---
r1c1, r1c2 = st.columns(2)
with r1c1:
    st.subheader("Equity Curve")
    st.plotly_chart(equity_curve_chart(eq_df), use_container_width=True)
    if eq_df.empty:
        st.caption("No trades in this period to plot.")
with r1c2:
    st.subheader("Drawdown")
    st.plotly_chart(drawdown_chart(dd_df), use_container_width=True)
    if dd_df.empty:
        st.caption("No drawdown data available.")

# --- Row 2: Win rate by DOW | P/L by strategy ---
r2c1, r2c2 = st.columns(2)
with r2c1:
    st.subheader("Win Rate by Day of Week")
    st.plotly_chart(win_rate_by_dow_chart(dow_df), use_container_width=True)
    if dow_df.empty:
        st.caption("Log more trades to see day-of-week trends.")
with r2c2:
    st.subheader("P/L by Strategy")
    st.plotly_chart(pnl_by_strategy_chart(strat_df), use_container_width=True)
    if strat_df.empty:
        st.caption("Assign strategies to trades to see this breakdown.")

# --- Row 3: Profit factor gauge | R-multiple histogram ---
r3c1, r3c2 = st.columns(2)
with r3c1:
    st.subheader("Profit Factor")
    st.plotly_chart(profit_factor_gauge(pf), use_container_width=True)
with r3c2:
    st.subheader("R-Multiple Distribution")
    st.plotly_chart(r_multiple_histogram(rr_df, median_rr=median_rr), use_container_width=True)
    if rr_df.empty:
        st.caption("Log trades with R-multiple to see distribution.")

# --- Bonus row: Emotion vs R | Setup breakdown ---
b1, b2 = st.columns(2)
with b1:
    st.subheader("Emotion vs. R-Multiple")
    st.plotly_chart(emotion_vs_rr_chart(emo_df), use_container_width=True)
    if emo_df.empty:
        st.caption("Add emotion labels to trades to see this chart.")
with b2:
    st.subheader("Setup Breakdown")
    st.plotly_chart(setup_breakdown_chart(setup_df), use_container_width=True)
    if setup_df.empty:
        st.caption("Assign setup types to trades to see this chart.")


def _fmt_pf(v: float) -> str:
    return "∞" if math.isinf(v) else f"{v:.2f}"


# --- Killzone Performance (Week 5 Phase 2) ---
st.markdown("---")
st.subheader("🎯 Killzone Performance")

kz_df = killzone_performance(df)
if kz_df.empty:
    st.caption("No killzone data yet. Tag trades with a killzone to see this breakdown.")
else:
    kc1, kc2 = st.columns([3, 2])
    with kc1:
        st.bar_chart(kz_df.set_index("killzone")["total_pnl"], height=300)
    with kc2:
        kz_disp = kz_df.copy()
        kz_disp["win_rate"] = (kz_disp["win_rate"] * 100).round(1).astype(str) + "%"
        kz_disp["avg_rr_realized"] = kz_disp["avg_rr_realized"].round(2)
        kz_disp["profit_factor"] = kz_disp["profit_factor"].apply(_fmt_pf)
        kz_disp["total_pnl"] = kz_disp["total_pnl"].round(2)
        st.dataframe(
            kz_disp[
                ["killzone", "trades", "win_rate", "avg_rr_realized", "profit_factor", "total_pnl"]
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
            cm_disp[["confirmation_model", "trades", "win_rate", "profit_factor", "total_pnl"]],
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
