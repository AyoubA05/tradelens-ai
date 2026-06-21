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

import math  # noqa: E402

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src.tradelens.services.metrics import (  # noqa: E402
    compute_basic_metrics,
    compute_equity_curve,
    consistency_score,
    get_last_n_trades,
    killzone_performance,
    period_deltas,
    split_periods,
    trade_of_the_week,
)
from src.tradelens.services.trade_service import (  # noqa: E402
    get_primary_screenshot,
    get_trades,
)
from src.tradelens.ui.components.charts import equity_curve_chart  # noqa: E402
from src.tradelens.ui.components.sidebar import render_sidebar  # noqa: E402
from src.tradelens.ui.components.theme import PLOTLY_TEMPLATE, inject_css  # noqa: E402
from src.tradelens.ui.components.ui import (  # noqa: E402
    empty_state,
    grade_chip,
    kpi_card,
    section_header,
)

st.set_page_config(
    page_title="TradeLens AI",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_css()

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
    trades = get_trades()
    df = pd.DataFrame([{c: getattr(t, c, None) for c in _DF_COLS} for t in trades])
    if df.empty:
        return df
    # Drop rows with no trade_date (legacy/empty rows would break date math).
    return df[df["trade_date"].notna() & (df["trade_date"] != "")].reset_index(
        drop=True
    )


@st.cache_data(show_spinner=False)
def _dashboard(version, df: pd.DataFrame) -> dict:
    """Expensive aggregations, cached on `version` = (trade_count, max_updated_at)
    so a delete+add (same count) still busts the cache."""
    current, prior = split_periods(df, days=30)
    return {
        "metrics": compute_basic_metrics(df),
        "consistency": consistency_score(df),
        "equity": compute_equity_curve(df),
        "killzone": killzone_performance(df),
        "deltas": period_deltas(current, prior),
        "trade_of_week": trade_of_the_week(df),
    }


def _fmt_delta(key: str, val):
    if val is None:
        return None, None
    sign = "+" if val >= 0 else "-"
    a = abs(val)
    if key == "net_pnl":
        text = f"{sign}${a:,.0f}"
    elif key == "win_rate":
        text = f"{sign}{a * 100:.1f} pts"
    elif key == "profit_factor":
        text = f"{sign}{a:.2f}"
    else:  # consistency
        text = f"{sign}{a:.1f}"
    return text, (val >= 0)


def _fmt_pf(pf) -> str:
    return "∞" if pf is not None and math.isinf(pf) else f"{pf:.2f}"


# ── Load data ─────────────────────────────────────────────────────
df = _load_df()

with st.sidebar:
    render_sidebar(df if not df.empty else None)

st.markdown(
    section_header("Dashboard", "Your trading performance at a glance"),
    unsafe_allow_html=True,
)

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

version = (len(df), max((str(v) for v in df["updated_at"].fillna("")), default=""))
data = _dashboard(version, df)
m = data["metrics"]
deltas = data["deltas"]
total = m["total_trades"]

# ── Hero KPI row ──────────────────────────────────────────────────
pnl_d_text, pnl_d_pos = _fmt_delta("net_pnl", deltas["net_pnl"])
wr_d_text, wr_d_pos = _fmt_delta("win_rate", deltas["win_rate"])
pf_d_text, pf_d_pos = _fmt_delta("profit_factor", deltas["profit_factor"])
cs_d_text, cs_d_pos = _fmt_delta("consistency", deltas["consistency"])

cs_value = f"{data['consistency']:.0f}" if total >= 5 else "—"

k1, k2, k3, k4 = st.columns(4)
k1.markdown(
    kpi_card("Net P&L", f"${m['total_pnl']:,.2f}", pnl_d_text, pnl_d_pos),
    unsafe_allow_html=True,
)
k2.markdown(
    kpi_card("Win Rate", f"{m['win_rate']:.1%}", wr_d_text, wr_d_pos),
    unsafe_allow_html=True,
)
k3.markdown(
    kpi_card("Profit Factor", _fmt_pf(m["profit_factor"]), pf_d_text, pf_d_pos),
    unsafe_allow_html=True,
)
k4.markdown(
    kpi_card("Consistency", cs_value, cs_d_text, cs_d_pos),
    unsafe_allow_html=True,
)
st.caption("Δ shown vs the previous 30 days.")

st.markdown("")

# ── Equity curve ──────────────────────────────────────────────────
st.markdown(section_header("Equity Curve"), unsafe_allow_html=True)
eq = data["equity"]
if not eq.empty:
    fig = equity_curve_chart(eq)
    fig.update_layout(template=PLOTLY_TEMPLATE)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.caption("Not enough data to plot an equity curve yet.")

st.markdown("")

# ── Two-up: Trade of the Week + Killzone performance ──────────────
left, right = st.columns([1, 1])

with left:
    st.markdown(section_header("Trade of the Week"), unsafe_allow_html=True)
    tow = data["trade_of_week"]
    if tow:
        chip = grade_chip(tow.get("grade"))
        asset = tow.get("asset") or "—"
        pnl = tow.get("pnl") or 0.0
        tdate = tow.get("trade_date") or ""
        st.markdown(
            '<div class="tl-kpi-card">'
            '<div style="display:flex;justify-content:space-between;'
            f'align-items:center"><span style="font-weight:600">{asset}</span>'
            f"{chip}</div>"
            f'<div class="tl-kpi-value" style="margin-top:6px">${pnl:,.2f}</div>'
            f'<div class="tl-kpi-label">{tdate}</div></div>',
            unsafe_allow_html=True,
        )
        shot = get_primary_screenshot(tow.get("id"))
        if shot and Path(shot).exists():
            st.image(shot, use_container_width=True)
    else:
        st.markdown(
            empty_state("No graded trades yet — grade a trade to feature it here."),
            unsafe_allow_html=True,
        )

with right:
    st.markdown(section_header("Killzone Performance"), unsafe_allow_html=True)
    kz = data["killzone"]
    if kz is not None and not kz.empty:
        view = kz.copy()
        view["win_rate"] = (view["win_rate"] * 100).round(1)
        st.dataframe(
            view[["killzone", "trades", "win_rate", "total_pnl"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "killzone": "Killzone",
                "trades": "Trades",
                "win_rate": st.column_config.NumberColumn("Win %", format="%.1f"),
                "total_pnl": st.column_config.NumberColumn("Net P&L", format="$%.0f"),
            },
        )
    else:
        st.caption("No killzone data yet.")

st.markdown("")

# ── Recent trades ─────────────────────────────────────────────────
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
st.dataframe(
    recent_display,
    use_container_width=True,
    hide_index=True,
    column_config={
        "P&L ($)": st.column_config.NumberColumn("P&L ($)", format="$%.2f"),
    },
)
