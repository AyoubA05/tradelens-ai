import sys
from pathlib import Path

# parents[3] of src/tradelens/ui/app.py  →  project root
_root = str(Path(__file__).resolve().parents[3])
if _root not in sys.path:
    sys.path.insert(0, _root)

from src.tradelens.db.init_db import init_db  # noqa: E402

# Idempotent: creates tables on first run, no-op if already exist.
# Required on Streamlit Cloud where SQLite starts fresh on each deploy.
init_db()
Path(__file__).resolve().parents[3].joinpath("data", "screenshots").mkdir(
    parents=True, exist_ok=True
)

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src.tradelens.services.metrics import (  # noqa: E402
    compute_basic_metrics,
    compute_expectancy,
    current_week_pnl,
    daily_equity_curve,
    format_profit_factor,
    get_last_n_trades,
    today_pnl,
)
from src.tradelens.services.demo import get_demo_df, is_demo  # noqa: E402
from src.tradelens.services.sample_data import count_sample_trades  # noqa: E402
from src.tradelens.services.trade_service import get_trades  # noqa: E402
from src.tradelens.ui.components.auth import (  # noqa: E402
    current_user_id,
    require_auth,
)
from src.tradelens.ui.components.charts import equity_curve_chart  # noqa: E402
from src.tradelens.ui.components.sidebar import render_sidebar  # noqa: E402
from src.tradelens.ui.components.demo_banner import render_demo_banner  # noqa: E402
from src.tradelens.ui.components.theme import (  # noqa: E402
    PLOTLY_TEMPLATE,
    TEAL,
    TERRA,
    inject_css,
)
from src.tradelens.ui.components.ui import (  # noqa: E402
    empty_state,
    kpi_card,
    section_header,
)

st.set_page_config(
    page_title="TradeLens AI",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_css()
require_auth()  # gate: shows the login page and halts here until signed in
render_demo_banner()

_DF_COLS = [
    "id",
    "trade_date",
    "asset",
    "direction",
    "result",
    "pnl",
    "rr_realized",
    "setup_type",
    "ai_grade",
    "user_grade",
    "killzone",
    "followed_rules",
    "mistake_tags",
    "htf_bias",
    "updated_at",
]


def _load_df() -> pd.DataFrame:
    trades = get_trades(user_id=current_user_id())
    df = pd.DataFrame([{c: getattr(t, c, None) for c in _DF_COLS} for t in trades])
    if df.empty:
        return df
    # Drop rows with no trade_date (legacy/empty rows would break date math).
    return df[df["trade_date"].notna() & (df["trade_date"] != "")].reset_index(
        drop=True
    )


def _pnl_color(v: float) -> str:
    """Teal for non-negative money, terra for losses."""
    return TEAL if v >= 0 else TERRA


# ── Load data ─────────────────────────────────────────────────────
df = _load_df()

# DEMO_MODE on a cold/empty DB: show rich synthetic data so the app is alive.
if df.empty and is_demo():
    df = get_demo_df()

render_sidebar()

st.markdown(
    section_header("Dashboard", "Your trading performance at a glance"),
    unsafe_allow_html=True,
)

if count_sample_trades(current_user_id()) > 0:
    st.info("🔬 Demo data is active. These are sample trades.")

# ── Empty state ───────────────────────────────────────────────────
if df.empty:
    st.markdown(
        empty_state(
            "No trades yet — log your first trade to see your dashboard come alive.",
            cta_label="Log a trade",
            cta_href="/NewTrade",
        ),
        unsafe_allow_html=True,
    )
    st.stop()

m = compute_basic_metrics(df)
t_pnl = today_pnl(df)
w_pnl = current_week_pnl(df)
exp = compute_expectancy(m)
pf_str = format_profit_factor(df)

# ── Row 1: KPI cards ──────────────────────────────────────────────
k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.markdown(
    kpi_card("Today's P&L", f"${t_pnl:,.2f}", value_color=_pnl_color(t_pnl)),
    unsafe_allow_html=True,
)
k2.markdown(
    kpi_card("This Week's P&L", f"${w_pnl:,.2f}", value_color=_pnl_color(w_pnl)),
    unsafe_allow_html=True,
)
k3.markdown(kpi_card("Win Rate", f"{m['win_rate']:.1%}"), unsafe_allow_html=True)
k4.markdown(kpi_card("Total Trades", f"{m['total_trades']}"), unsafe_allow_html=True)
k5.markdown(
    kpi_card(
        "Profit Factor",
        pf_str,
        tooltip="No losses yet" if pf_str == "∞" else None,
    ),
    unsafe_allow_html=True,
)
k6.markdown(
    kpi_card("Expectancy", f"${exp:,.2f}", value_color=_pnl_color(exp)),
    unsafe_allow_html=True,
)

st.markdown("")

# ── Row 2: Equity curve (full width) ──────────────────────────────
st.markdown(section_header("Equity Curve"), unsafe_allow_html=True)
eq = daily_equity_curve(df)
if not eq.empty:
    fig = equity_curve_chart(eq)
    fig.update_layout(template=PLOTLY_TEMPLATE)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.caption("Not enough data to plot an equity curve yet.")

st.markdown("")

# ── Row 3: Recent trades (last 5) ─────────────────────────────────
st.markdown(section_header("Recent Trades"), unsafe_allow_html=True)
recent = get_last_n_trades(df, 5)
RECENT_COLS = ["trade_date", "asset", "direction", "result", "pnl", "setup_type"]
recent_display = recent[[c for c in RECENT_COLS if c in recent.columns]].rename(
    columns={
        "trade_date": "Date",
        "asset": "Asset",
        "direction": "Direction",
        "result": "Result",
        "pnl": "P&L ($)",
        "setup_type": "Setup",
    }
)
# Readable blanks instead of raw None in the text columns (leave P&L numeric).
_text_cols = [c for c in recent_display.columns if c != "P&L ($)"]
recent_display[_text_cols] = recent_display[_text_cols].fillna("—")
st.dataframe(
    recent_display,
    use_container_width=True,
    hide_index=True,
    column_config={
        "P&L ($)": st.column_config.NumberColumn("P&L ($)", format="$%.2f"),
    },
)

st.markdown("")

# ── Row 4: Quick actions ──────────────────────────────────────────
st.markdown(section_header("Quick Actions"), unsafe_allow_html=True)
qa1, qa2, qa3 = st.columns(3)
if qa1.button("Log Trade", use_container_width=True):
    st.switch_page("pages/1_NewTrade.py")
if qa2.button("Open Journal", use_container_width=True):
    st.switch_page("pages/2_Trades.py")
if qa3.button("Review Analytics", use_container_width=True):
    st.switch_page("pages/4_Analytics.py")
