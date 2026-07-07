import sys
import math
import datetime
from pathlib import Path

# parents[4] of src/tradelens/ui/pages/*.py  →  project root
_root = str(Path(__file__).resolve().parents[4])
if _root not in sys.path:
    sys.path.insert(0, _root)

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src.tradelens.services.demo import get_demo_df, is_demo  # noqa: E402
from src.tradelens.services.metrics import (  # noqa: E402
    by_day_of_week,
    by_session,
    compute_basic_metrics,
    compute_breakdown,
    compute_equity_curve,
    compute_expectancy,
    compute_max_drawdown,
    compute_profit_factor_raw,
    drawdown_series,
    equity_curve_series,
)
from src.tradelens.services.strategy import get_active_strategy  # noqa: E402
from src.tradelens.services.trade_service import get_trades  # noqa: E402
from src.tradelens.ui.components.auth import current_user_id, require_auth  # noqa: E402
from src.tradelens.ui.components.calendar_view import render_calendar  # noqa: E402
from src.tradelens.ui.components.charts import (  # noqa: E402
    drawdown_chart,
    equity_curve_chart,
    pnl_by_dow_chart,
    pnl_by_emotion_chart,
    pnl_by_session_chart,
    risk_over_time_chart,
    session_dow_heatmap,
    win_rate_rules_chart,
)
from src.tradelens.ui.components.demo_banner import render_demo_banner  # noqa: E402
from src.tradelens.ui.components.sidebar import render_sidebar  # noqa: E402
from src.tradelens.ui.components.theme import PLOTLY_TEMPLATE, inject_css  # noqa: E402
from src.tradelens.ui.components.ui import empty_state, section_header  # noqa: E402

st.set_page_config(page_title="Analytics", layout="wide")
inject_css()
require_auth()
render_demo_banner()
render_sidebar()
st.markdown(
    section_header("Analytics", "Your trading performance, sectioned for clarity"),
    unsafe_allow_html=True,
)

_active_strategy = get_active_strategy()
if _active_strategy:
    st.caption(f"Strategy: {_active_strategy.get('name', '—')}")


def _fmt_pf(v) -> str:
    return "∞" if isinstance(v, float) and math.isinf(v) else f"{float(v):.2f}"


def _ratio(v) -> str:
    """An R value as a readable ratio string (1.8 → '1.8:1'). 0/None → '—'."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "—"
    return f"{f:g}:1" if f else "—"


def _styled(fig):
    fig.update_layout(template=PLOTLY_TEMPLATE)
    return fig


def _section(title: str, description: str) -> None:
    st.divider()
    st.markdown(section_header(title), unsafe_allow_html=True)
    st.caption(description)


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
                "risk_amount": t.risk_amount,
                "pnl": t.pnl,
                "result": t.result,
                "killzone": t.killzone,
                "htf_bias": t.htf_bias,
                "followed_rules": t.followed_rules,
            }
            for t in trades
        ]
    )


# ── Filters ───────────────────────────────────────────────────────
today = datetime.date.today()
fcol1, fcol2 = st.columns(2)
with fcol1:
    start_date = st.date_input(
        "From", value=today - datetime.timedelta(days=90), key="an_from"
    )
with fcol2:
    end_date = st.date_input("To", value=today, key="an_to")

df_raw = _load_df(str(start_date), str(end_date), current_user_id())
if df_raw.empty and is_demo():
    df_raw = get_demo_df()

# Normalize the column set so demo data (a different shape) and real trades both
# render every section without KeyErrors — missing columns become all-NaN.
if not df_raw.empty:
    for _col in (
        "risk_amount",
        "followed_rules",
        "emotions_before",
        "session",
        "day_of_week",
        "setup_type",
        "result",
        "rr_realized",
        "strategy_used",
        "asset",
    ):
        if _col not in df_raw.columns:
            df_raw[_col] = pd.NA

if df_raw.empty:
    st.markdown(
        empty_state(
            "No trades in this range yet — log a trade to unlock your analytics.",
            cta_label="Log a trade",
            cta_href="/NewTrade",
        ),
        unsafe_allow_html=True,
    )
    st.stop()

fc1, fc2, fc3 = st.columns(3)
with fc1:
    sel_assets = st.multiselect(
        "Asset", sorted(df_raw["asset"].dropna().unique().tolist()), key="an_asset"
    )
with fc2:
    sel_sessions = st.multiselect(
        "Session",
        sorted(df_raw["session"].dropna().unique().tolist()),
        key="an_session",
    )
with fc3:
    sel_strats = st.multiselect(
        "Strategy",
        sorted(df_raw["strategy_used"].dropna().unique().tolist()),
        key="an_strat",
    )

df = df_raw.copy()
if sel_assets:
    df = df[df["asset"].isin(sel_assets)]
if sel_sessions:
    df = df[df["session"].isin(sel_sessions)]
if sel_strats:
    df = df[df["strategy_used"].isin(sel_strats)]

if df.empty:
    st.warning("No trades match the selected filters. Adjust the range or filters.")
    st.stop()


# ══════════════════════════════════════════════════════════════════
# 1 · PERFORMANCE OVERVIEW
# ══════════════════════════════════════════════════════════════════
_section("Performance Overview", "Headline results across the selected period.")
m = compute_basic_metrics(df)
pf = compute_profit_factor_raw(df)
k1, k2, k3, k4 = st.columns(4)
k1.metric("Total P&L", f"${m['total_pnl']:,.2f}")
k2.metric("Win Rate", f"{m['win_rate']:.1%}")
k3.metric("Profit Factor", _fmt_pf(pf))
k4.metric("Expectancy", f"${compute_expectancy(m):,.2f}")
k5, k6, k7, k8 = st.columns(4)
k5.metric("Avg Win", f"${m['avg_win']:,.2f}")
k6.metric("Avg Loss", f"${m['avg_loss']:,.2f}")
k7.metric("Largest Win", f"${m['best_trade']:,.2f}")
k8.metric("Largest Loss", f"${m['worst_trade']:,.2f}")

eq_df = equity_curve_series(df)
if not eq_df.empty:
    st.markdown("**Equity Curve**")
    st.plotly_chart(
        _styled(equity_curve_chart(eq_df)), use_container_width=True, key="an_eq"
    )


# ══════════════════════════════════════════════════════════════════
# 2 · RISK ANALYSIS
# ══════════════════════════════════════════════════════════════════
_section(
    "Risk Analysis",
    "How much you risk, your reward ratios, and your worst drawdown.",
)
sess_df = by_session(df)
best_sess = worst_sess = None
if not sess_df.empty:
    best_sess = sess_df.loc[sess_df["total_pnl"].idxmax()]
    worst_sess = sess_df.loc[sess_df["total_pnl"].idxmin()]
max_dd = compute_max_drawdown(compute_equity_curve(df))

r1, r2, r3, r4 = st.columns(4)
r1.metric("Avg R:R", _ratio(m.get("avg_rr_realized")))
r2.metric("Avg T-Multiple", _ratio(m.get("avg_rr_realized")))
r3.metric("Max Drawdown", f"${max_dd:,.2f}")
if best_sess is not None:
    r4.metric(
        "Best Session", str(best_sess["session"]), f"${best_sess['total_pnl']:,.0f}"
    )

if worst_sess is not None:
    bw1, _bw2 = st.columns([1, 3])
    bw1.metric(
        "Worst Session", str(worst_sess["session"]), f"${worst_sess['total_pnl']:,.0f}"
    )

rc1, rc2 = st.columns(2)
with rc1:
    st.markdown("**Risk ($) per Trade Over Time**")
    if df["risk_amount"].notna().any():
        st.plotly_chart(
            _styled(risk_over_time_chart(df)), use_container_width=True, key="an_risk"
        )
    else:
        st.caption("Log a Risk ($) on your trades to see this trend.")
with rc2:
    st.markdown("**Drawdown**")
    dd_df = drawdown_series(df)
    if not dd_df.empty:
        st.plotly_chart(
            _styled(drawdown_chart(dd_df)), use_container_width=True, key="an_dd"
        )
    else:
        st.caption("No drawdown yet — log a few more trades to chart it.")


# ══════════════════════════════════════════════════════════════════
# 3 · TIME & SESSION ANALYSIS
# ══════════════════════════════════════════════════════════════════
_section(
    "Time & Session Analysis",
    "When you trade best — by market session and day of week.",
)
dow_df = by_day_of_week(df)
ts1, ts2 = st.columns(2)
with ts1:
    st.markdown("**P&L by Session**")
    if not sess_df.empty:
        st.plotly_chart(
            _styled(pnl_by_session_chart(sess_df)),
            use_container_width=True,
            key="an_sess",
        )
    else:
        st.caption("Sessions are auto-detected from entry time on new trades.")
with ts2:
    st.markdown("**P&L by Day of Week**")
    if not dow_df.empty:
        st.plotly_chart(
            _styled(pnl_by_dow_chart(dow_df)), use_container_width=True, key="an_dow"
        )
    else:
        st.caption("Log more trades to see day-of-week trends.")

if not sess_df.empty and not dow_df.empty:
    st.markdown("**Net P&L Heatmap — Session × Day of Week**")
    st.plotly_chart(
        _styled(session_dow_heatmap(df)), use_container_width=True, key="an_heat"
    )


# ══════════════════════════════════════════════════════════════════
# 4 · SETUP PERFORMANCE
# ══════════════════════════════════════════════════════════════════
_section(
    "Setup Performance",
    "Which setups carry your edge — sortable by any column (click a header).",
)
setup_df = compute_breakdown(df, "setup_type")
if setup_df.empty:
    st.caption("Assign setup types to trades to see this breakdown.")
else:
    setup_df = setup_df.copy()
    setup_df["profit_factor"] = setup_df["setup_type"].map(
        lambda s: compute_profit_factor_raw(df[df["setup_type"] == s])
    )
    table = setup_df[
        ["setup_type", "trades", "win_rate", "avg_pnl", "profit_factor", "total_pnl"]
    ].rename(
        columns={
            "setup_type": "Setup",
            "trades": "Trades",
            "win_rate": "Win Rate",
            "avg_pnl": "Avg P&L",
            "profit_factor": "Profit Factor",
            "total_pnl": "Total P&L",
        }
    )
    table["Profit Factor"] = table["Profit Factor"].map(_fmt_pf)
    # NumberColumn percent format expects 0–100; win_rate is a 0–1 fraction.
    table["Win Rate"] = (table["Win Rate"] * 100).round(1)
    st.dataframe(
        table,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Win Rate": st.column_config.NumberColumn("Win Rate", format="%.1f%%"),
            "Avg P&L": st.column_config.NumberColumn("Avg P&L", format="$%.2f"),
            "Total P&L": st.column_config.NumberColumn("Total P&L", format="$%.2f"),
        },
    )


# ══════════════════════════════════════════════════════════════════
# 5 · EMOTIONAL PATTERNS
# ══════════════════════════════════════════════════════════════════
_section(
    "Emotional Patterns",
    "How discipline and mindset show up in your results.",
)
followed = pd.to_numeric(df.get("followed_rules"), errors="coerce")
res = (
    df["result"].fillna("").astype(str).str.lower()
    if "result" in df
    else pd.Series(dtype=str)
)
win = res.eq("win")
foll_mask = followed == 1
broke_mask = followed == 0
foll_n, broke_n = int(foll_mask.sum()), int(broke_mask.sum())

ep1, ep2 = st.columns(2)
with ep1:
    st.markdown("**Win Rate — Followed Rules vs Broke Rules**")
    if foll_n or broke_n:
        foll_wr = float(win[foll_mask].mean()) if foll_n else 0.0
        broke_wr = float(win[broke_mask].mean()) if broke_n else 0.0
        st.plotly_chart(
            _styled(win_rate_rules_chart(foll_wr, broke_wr, foll_n, broke_n)),
            use_container_width=True,
            key="an_rules",
        )
    else:
        st.caption("Answer 'Followed your rules?' on trades to see this.")
with ep2:
    st.markdown("**P&L by Emotional State**")
    emo_df = compute_breakdown(df, "emotions_before")
    if not emo_df.empty:
        st.plotly_chart(
            _styled(pnl_by_emotion_chart(emo_df)),
            use_container_width=True,
            key="an_emo",
        )
    else:
        st.caption("Tag your pre-trade emotion to see this breakdown.")


# ── Calendar (kept, secondary) ────────────────────────────────────
st.divider()
with st.expander("📅 Calendar view"):
    render_calendar(df_raw)
