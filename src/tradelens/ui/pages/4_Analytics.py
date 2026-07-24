import sys
import math
import datetime
from html import escape
from pathlib import Path

# parents[4] of src/tradelens/ui/pages/*.py  →  project root
_root = str(Path(__file__).resolve().parents[4])
if _root not in sys.path:
    sys.path.insert(0, _root)

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src.tradelens.services.demo import get_demo_df, is_demo  # noqa: E402
from src.tradelens.services.metrics import (  # noqa: E402
    outcome_masks,
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
from src.tradelens.ui.components.data_state import (  # noqa: E402
    enough_categories,
    render_data_state,
    sample_state,
    trades_needed,
)
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
from src.tradelens.ui.design_system import (  # noqa: E402
    inject_design_system,
    render_badge,
    render_empty_state,
    render_section_header,
)

st.set_page_config(page_title="Analytics", layout="wide")
inject_css()
inject_design_system()  # design_system.py wins ties (injected after theme)
require_auth()
uid = current_user_id()
render_demo_banner()
render_sidebar()
st.markdown(
    render_section_header(
        "Analytics", "Your trading performance, sectioned for clarity"
    ),
    unsafe_allow_html=True,
)

_active_strategy = get_active_strategy(uid) if uid is not None else None
if _active_strategy and _active_strategy.get("name"):
    st.markdown(
        render_badge(_active_strategy["name"], "primary"),
        unsafe_allow_html=True,
    )


def _fmt_pf(v, total_pnl=None) -> str:
    """PF display convention (app-wide): wins with no losses → '∞';
    a breakeven-only slice (0 wins / 0 losses = undefined) → 'N/A'."""
    if isinstance(v, float) and math.isinf(v):
        return "∞"
    if float(v) == 0.0 and total_pnl is not None and float(total_pnl) == 0.0:
        return "N/A"
    return f"{float(v):.2f}"


def _ratio(v) -> str:
    """An R value as a readable ratio string (1.8 → '1.8:1'). 0/None → '—'."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "—"
    if math.isnan(f):
        return "—"
    return f"{f:g}:1" if f else "—"


def _money(v) -> str:
    """App-wide money convention: -$301.00, never $-301.00 (matches
    Journal _fmt_money and the KPI-card formatter)."""
    v = float(v)
    return f"-${abs(v):,.2f}" if v < 0 else f"${v:,.2f}"


def _styled(fig):
    """Apply the shared TradeLens template (colors, grid, fonts, tooltips
    all come from design_system.PLOTLY_TEMPLATE); margins are the only
    page-specific setting."""
    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        margin=dict(l=16, r=16, t=16, b=16),
    )
    return fig


def _chart(fig, key: str, title: str = "") -> None:
    """Card-wrapped chart. st.container(border=True) is the version-safe
    tl-form-card equivalent (stPlotlyChart is not in the proven-selector
    set, and Streamlit elements can't sit inside an HTML string wrapper)."""
    with st.container(border=True):
        if title:
            st.markdown(
                f'<div class="tl-chart-title">{escape(title)}</div>',
                unsafe_allow_html=True,
            )
        # plotly_chart has no width= on streamlit 1.50 — use_container_width
        # stays here until the pin bumps (unlike buttons/images/dataframes).
        st.plotly_chart(
            _styled(fig),
            use_container_width=True,
            key=key,
            config={"displayModeBar": False},
        )


def _empty(icon: str, title: str, body: str) -> None:
    st.markdown(render_empty_state(icon, title, body), unsafe_allow_html=True)


def _one_category_note(breakdown: pd.DataFrame, column: str, noun: str) -> None:
    """State a single-category breakdown instead of charting it.

    One full-height bar carries no comparison — it just restates its own
    axis label at maximum visual volume.
    """
    row = breakdown.iloc[0]
    total = float(row.get("total_pnl") or 0.0)
    trades = int(row.get("trades") or 0)
    render_data_state(
        f"One {noun} so far: {escape(str(row[column]))}",
        f"{trades} trade{'s' if trades != 1 else ''}, {_money(total)} net. "
        f"Trade another {noun} to compare them.",
        "◆",
    )


def _section(title: str, description: str) -> None:
    # The section header's teal top-rule is the visual break — no divider.
    st.markdown(render_section_header(title, description), unsafe_allow_html=True)


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

df_raw = _load_df(str(start_date), str(end_date), uid)
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
    _empty(
        "◆",
        "No trades in this range yet",
        "Log a trade to unlock your analytics.",
    )
    try:
        st.page_link("pages/1_NewTrade.py", label="Log a trade →")
    except Exception:  # noqa: BLE001 — registry-less boots (AppTest) raise
        st.markdown(
            '<a href="/NewTrade" target="_self">Log a trade →</a>',
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
    _empty("◆", "No matching trades", "Adjust the date range or filters.")
    st.stop()

# One shared decision about what this sample has earned the right to show,
# so every section below agrees rather than each guessing on its own.
_state = sample_state(df)


# ══════════════════════════════════════════════════════════════════
# 1 · PERFORMANCE OVERVIEW
# ══════════════════════════════════════════════════════════════════
_section("Performance Overview", "Headline results across the selected period.")
m = compute_basic_metrics(df)
pf = compute_profit_factor_raw(df)
k1, k2, k3, k4 = st.columns(4)
k1.metric("Total P&L", _money(m["total_pnl"]))
k2.metric("Win Rate", f"{m['win_rate']:.1%}")
k3.metric("Profit Factor", _fmt_pf(pf, m["total_pnl"]))
k4.metric("Expectancy", _money(compute_expectancy(m)))
k5, k6, k7, k8 = st.columns(4)
k5.metric("Avg Win", _money(m["avg_win"]))
k6.metric("Avg Loss", _money(m["avg_loss"]))
k7.metric("Largest Win", _money(m["best_trade"]))
k8.metric("Largest Loss", _money(m["worst_trade"]))

eq_df = equity_curve_series(df)
if not _state.show_series:
    render_data_state(
        "Add one more dated trade",
        "Two trading dates are needed to draw a meaningful curve.",
        "📈",
    )
elif not eq_df.empty:
    _chart(equity_curve_chart(eq_df), "an_eq", "Equity Curve")
else:
    _empty("📈", "Equity curve not available", "Log P&L on trades to chart it.")


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

_median_rr = pd.to_numeric(df["rr_realized"], errors="coerce").dropna().median()
r1, r2, r3, r4 = st.columns(4)
r1.metric("Avg R:R", _ratio(m.get("avg_rr_realized")))
r2.metric("Median R:R", _ratio(_median_rr))
r3.metric("Max Drawdown", _money(max_dd) if _state.show_series else "—")
# "Best" implies a field to have been best of. With one session in range,
# best and worst are the same row — say so instead of ranking it.
_sessions_comparable = enough_categories(sess_df, "session")
if best_sess is not None:
    r4.metric(
        "Best Session" if _sessions_comparable else "Only session in this range",
        str(best_sess["session"]),
        f"${best_sess['total_pnl']:,.0f}",
    )

if worst_sess is not None and _sessions_comparable:
    # Danger reads only for truly negative outcomes: a positive "worst"
    # session is just the lowest — neutral label, neutral delta color.
    _worst_pnl = float(worst_sess["total_pnl"])
    _worst_label = "Worst Session" if _worst_pnl < 0 else "Lowest Session"
    bw1, _bw2 = st.columns([1, 3])
    bw1.metric(
        _worst_label,
        str(worst_sess["session"]),
        f"${_worst_pnl:,.0f}",
        delta_color="normal" if _worst_pnl < 0 else "off",
    )

rc1, rc2 = st.columns(2)
with rc1:
    if not _state.show_series:
        render_data_state(
            "Risk trend needs a second date",
            "A trend over time needs at least two trading dates.",
            "📏",
        )
    elif df["risk_amount"].notna().any():
        _chart(risk_over_time_chart(df), "an_risk", "Risk ($) per Trade Over Time")
    else:
        _empty("📏", "Risk trend not available", "Log Risk ($) to unlock.")
with rc2:
    dd_df = drawdown_series(df)
    if not _state.show_series:
        render_data_state(
            "Drawdown needs a second date",
            "A drawdown axis drawn from one trading day has no peak to fall from.",
            "📉",
        )
    elif not dd_df.empty:
        _chart(drawdown_chart(dd_df), "an_dd", "Drawdown")
    else:
        _empty(
            "📉",
            "Drawdown not available",
            "Log a few more trades to chart it.",
        )


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
    if sess_df.empty:
        _empty(
            "🕐",
            "Session data not available",
            "Sessions are auto-detected from entry time on new trades.",
        )
    elif not _sessions_comparable:
        _one_category_note(sess_df, "session", "session")
    else:
        _chart(pnl_by_session_chart(sess_df), "an_sess", "P&L by Session")
with ts2:
    _dow_comparable = enough_categories(dow_df, "day_of_week")
    if dow_df.empty:
        _empty(
            "📅",
            "Day-of-week data not available",
            "Log more trades to see day-of-week trends.",
        )
    elif not _dow_comparable:
        _one_category_note(dow_df, "day_of_week", "day")
    else:
        _chart(pnl_by_dow_chart(dow_df), "an_dow", "P&L by Day of Week")

# A heatmap of a single cell is a coloured square, not a pattern.
if _sessions_comparable and _dow_comparable:
    _chart(
        session_dow_heatmap(df),
        "an_heat",
        "Net P&L Heatmap — Session × Day of Week",
    )
else:
    render_data_state(
        "Heatmap needs more spread",
        "Trade across at least two sessions and two days to fill this grid.",
        "🗓",
    )


# ══════════════════════════════════════════════════════════════════
# 4 · SETUP PERFORMANCE
# ══════════════════════════════════════════════════════════════════
_section(
    "Setup Performance",
    "Which setups carry your edge — ranked by total P&L.",
)
setup_df = compute_breakdown(df, "setup_type")
if setup_df.empty:
    _empty(
        "🧩",
        "Setup data not available",
        "Assign setup types to trades to see this leaderboard.",
    )
elif not _state.show_patterns:
    render_data_state(
        f"{trades_needed(_state, 5)} more trades to rank setups",
        "Ranking setups on a handful of trades mostly ranks luck.",
        "🧩",
    )
else:
    # compute_breakdown returns rows sorted by total_pnl desc → rank order.
    _lb_rows = []
    for _rank, _r in enumerate(setup_df.itertuples(index=False), start=1):
        _pf = compute_profit_factor_raw(df[df["setup_type"] == _r.setup_type])
        _wr = float(_r.win_rate or 0.0)
        _wr_cls = " pnl-pos" if _wr >= 0.5 else ""
        try:
            _avg = float(_r.avg_pnl)
        except (TypeError, ValueError):
            _avg = None
        if _avg is None or pd.isna(_avg):
            _avg_cls, _avg_txt = "", "—"
        else:
            _avg_cls = " pnl-pos" if _avg > 0 else (" pnl-neg" if _avg < 0 else "")
            _avg_txt = f"-${abs(_avg):,.2f}" if _avg < 0 else f"${_avg:,.2f}"
        _lb_rows.append(
            "<tr>"
            f'<td class="mono">{_rank}</td>'
            f"<td>{escape(str(_r.setup_type))}</td>"
            f'<td class="mono num">{int(_r.trades)}</td>'
            f'<td class="mono num{_wr_cls}">{_wr:.1%}</td>'
            f'<td class="mono num{_avg_cls}">{_avg_txt}</td>'
            f'<td class="mono num">{_fmt_pf(_pf, _r.total_pnl)}</td>'
            "</tr>"
        )
    st.markdown(
        '<div class="tl-form-card"><div class="tl-table-wrap">'
        '<table class="tl-table"><thead><tr>'
        '<th>Rank</th><th>Setup</th><th class="num">Trades</th>'
        '<th class="num">Win Rate</th><th class="num">Avg P&amp;L</th>'
        '<th class="num">PF</th>'
        f'</tr></thead><tbody>{"".join(_lb_rows)}</tbody></table></div></div>',
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════
# 5 · EMOTIONAL PATTERNS
# ══════════════════════════════════════════════════════════════════
_section(
    "Emotional Patterns",
    "How discipline and mindset show up in your results.",
)
followed = pd.to_numeric(df.get("followed_rules"), errors="coerce")
# Same canonical rule as every other metric on this page: signed P&L
# classifies rows that have it, the label covers only rows that don't.
win, _loss_mask, _be_mask = outcome_masks(df)
foll_mask = followed == 1
broke_mask = followed == 0
foll_n, broke_n = int(foll_mask.sum()), int(broke_mask.sum())

ep1, ep2 = st.columns(2)
with ep1:
    if not (foll_n or broke_n):
        _empty(
            "📐",
            "Rule data not available",
            "Answer 'Followed your rules?' when logging to see this.",
        )
    elif not (foll_n and broke_n):
        # Both sides must exist, or the "comparison" is one bar against zero.
        _kept = "followed" if foll_n else "broke"
        render_data_state(
            "Nothing to compare yet",
            f"Every logged trade so far {_kept} your rules. The comparison "
            "appears once both cases exist.",
            "📐",
        )
    else:
        foll_wr = float(win[foll_mask].mean())
        broke_wr = float(win[broke_mask].mean())
        _chart(
            win_rate_rules_chart(foll_wr, broke_wr, foll_n, broke_n),
            "an_rules",
            "Win Rate — Followed Rules vs Broke Rules",
        )
with ep2:
    emo_df = compute_breakdown(df, "emotions_before")
    if emo_df.empty:
        _empty(
            "🧠",
            "Emotion data not available",
            "Fill Psychology section when logging.",
        )
    elif not enough_categories(emo_df, "emotions_before"):
        _one_category_note(emo_df, "emotions_before", "emotional state")
    else:
        _chart(pnl_by_emotion_chart(emo_df), "an_emo", "P&L by Emotional State")


# ══════════════════════════════════════════════════════════════════
# 6 · CALENDAR VIEW
# ══════════════════════════════════════════════════════════════════
_section("Calendar View", "Daily P&L across the month, at a glance.")
render_calendar(df_raw)
