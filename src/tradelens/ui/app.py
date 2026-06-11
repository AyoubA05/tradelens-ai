import sys
from pathlib import Path

# parents[3] of src/tradelens/ui/app.py  →  project root
_root = str(Path(__file__).resolve().parents[3])
if _root not in sys.path:
    sys.path.insert(0, _root)

from src.tradelens.db.init_db import init_db

# Idempotent: creates tables on first run, no-op if already exist.
# Required on Streamlit Cloud where SQLite starts fresh on each deploy.
init_db()
Path(__file__).resolve().parents[3].joinpath("data", "screenshots").mkdir(
    parents=True, exist_ok=True
)

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.tradelens.services.metrics import (
    compute_basic_metrics,
    compute_equity_curve,
    get_last_n_trades,
)
from src.tradelens.services.trade_service import get_trades

st.set_page_config(
    page_title="TradeLens AI",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar ───────────────────────────────────────────────────────
with st.sidebar:
    st.title("📊 TradeLens AI")
    st.markdown("---")
    st.markdown("🏠 **Home**")
    st.markdown("➕ New Trade")
    st.markdown("📋 Trades")
    st.markdown("📅 Calendar")
    st.markdown("📈 Analytics")
    st.markdown("🎯 Strategy")
    st.markdown("📝 Weekly Review")
    st.markdown("⚙️ Settings")

# ── Header ────────────────────────────────────────────────────────
st.title("TradeLens AI")
st.caption("Your AI-Powered Trading Journal")
st.markdown("---")

# ── Load data ─────────────────────────────────────────────────────
trades = get_trades()

if not trades:
    st.info("No trades yet. Log your first trade on the New Trade page.")
    st.stop()

df = pd.DataFrame([
    {
        "trade_date":  t.trade_date,
        "asset":       t.asset,
        "direction":   t.direction,
        "result":      t.result,
        "pnl":         t.pnl,
        "rr_realized": t.rr_realized,
        "setup_type":  t.setup_type,
    }
    for t in trades
])

# Drop rows with no trade_date — old test rows without a date set
df = df[df["trade_date"].notna() & (df["trade_date"] != "")]

if df.empty:
    st.info("No trades yet. Log your first trade on the New Trade page.")
    st.stop()

m = compute_basic_metrics(df)

# ── KPI cards ─────────────────────────────────────────────────────
k1, k2, k3, k4 = st.columns(4)
k1.metric("Total P/L",      f"${m['total_pnl']:,.2f}")
k2.metric("Win Rate",       f"{m['win_rate']:.1%}")
k3.metric("Total Trades",   m["total_trades"])
k4.metric("Profit Factor",  f"{m['profit_factor']:.2f}")

st.markdown("")

# ── Equity curve ──────────────────────────────────────────────────
st.subheader("Equity Curve")

eq = compute_equity_curve(df)

if not eq.empty:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=eq["trade_date"],
        y=eq["cumulative_pnl"],
        mode="lines",
        fill="tozeroy",
        line=dict(color="#20808D", width=2),
        fillcolor="rgba(32, 128, 141, 0.12)",
        hovertemplate="Date: %{x}<br>Cumulative P/L: $%{y:,.2f}<extra></extra>",
    ))
    fig.add_hline(
        y=0,
        line_dash="dash",
        line_color="rgba(128, 128, 128, 0.5)",
        line_width=1,
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=8, b=0),
        xaxis=dict(showgrid=False, title=None),
        yaxis=dict(
            showgrid=True,
            gridcolor="rgba(200, 200, 200, 0.3)",
            title=None,
            tickprefix="$",
        ),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)

st.markdown("")

# ── Recent trades ─────────────────────────────────────────────────
st.subheader("Recent Trades")

recent = get_last_n_trades(df, 5)
RECENT_COLS = ["trade_date", "asset", "direction", "result", "pnl", "setup_type"]
recent_display = recent[[c for c in RECENT_COLS if c in recent.columns]]
recent_display = recent_display.rename(columns={
    "trade_date": "Date",
    "asset":      "Asset",
    "direction":  "Direction",
    "result":     "Result",
    "pnl":        "P&L ($)",
    "setup_type": "Setup",
})

st.dataframe(recent_display, use_container_width=True, hide_index=True)
