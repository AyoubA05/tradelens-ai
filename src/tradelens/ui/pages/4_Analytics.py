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
from src.tradelens.ui.components.trade_calendar import (  # noqa: E402
    render_trade_calendar,
)
from src.tradelens.ui.components.data_state import (  # noqa: E402
    enough_categories,
    has_variation,
    render_data_state,
    sample_state,
    trades_needed,
)
from src.tradelens.ui.components.charts import (  # noqa: E402
    add_sample_annotation,
    apply_chart_stage,
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
from src.tradelens.ui.components.sidebar import (  # noqa: E402
    render_sidebar,
    route_href,
)
from src.tradelens.ui.components.theme import inject_css  # noqa: E402
from src.tradelens.ui.components.workspace import (  # noqa: E402
    EvidenceItem,
    MetricItem,
    render_editorial_readout,
    render_kpi_strip,
    render_section_header,
    render_workspace_header,
)
from src.tradelens.ui.design_system import (  # noqa: E402
    inject_design_system,
    render_empty_state,
)

st.set_page_config(page_title="Analytics", layout="wide")
inject_css()
inject_design_system()  # design_system.py wins ties (injected after theme)
require_auth()
uid = current_user_id()
render_demo_banner()
render_sidebar()
_active_strategy = get_active_strategy(uid) if uid is not None else None
_strategy_name = (_active_strategy or {}).get("name")

# ── Lenses ────────────────────────────────────────────────────────
# One question at a time. The old page stacked six sections, so reaching
# the one a trader wanted meant scrolling past four charts answering
# questions they had not asked.
ANALYTICS_LENSES = ("Performance", "Risk", "Timing", "Setups")
_LENS_KEY = "analytics_lens"
_LENS_WIDGET_KEY = "analytics_lens_pick"

_LENS_QUESTIONS = {
    "Performance": "How did this period actually go?",
    "Risk": "How much was at stake, and what did it cost?",
    "Timing": "When does the edge show up?",
    "Setups": "Which setups carry it?",
}

st.markdown(
    render_workspace_header(
        "Analytics",
        "One question at a time, with the evidence behind the answer.",
        eyebrow=_strategy_name,
    ),
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


def _tone(value) -> str:
    """Semantic tone for a signed figure. Zero is neutral, not positive."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "neutral"
    if pd.isna(v):
        return "neutral"
    return "positive" if v > 0 else "negative" if v < 0 else "neutral"


def _chart(fig, key: str, title: str = "", *, summary: str, compact: bool = False):
    """Render one figure on the shared dark instrument stage.

    Framing lives in charts.apply_chart_stage, so every figure on the page —
    and on any future page — gets the same grid, typography, margins and
    height rather than whatever its call site happened to set.

    ``summary`` is required, not optional. Plotly paints into a canvas and an
    SVG of unlabelled paths: a screen reader gets the title and nothing about
    what the chart shows, and hover tooltips need a pointer. Spec §12 asks
    every chart to carry a text summary of its key insight, and a keyword
    that can be forgotten is one that will be — so the signature refuses a
    figure that has no sentence describing it.
    """
    with st.container(border=True):
        st.markdown(
            f'<p class="tl-visually-hidden">{escape(summary)}</p>',
            unsafe_allow_html=True,
        )
        # plotly_chart has no width= on streamlit 1.50 — use_container_width
        # stays here until the pin bumps (unlike buttons/images/dataframes).
        # theme=None keeps the dark chart stage; the default
        # theme="streamlit" repaints the figure in the app's own (now light)
        # theme, which put bright teal marks on near-white.
        st.plotly_chart(
            apply_chart_stage(fig, title=title or None, compact=compact),
            use_container_width=True,
            key=key,
            theme=None,
            config={"displayModeBar": False},
        )


def _ranked_table(headers: list, rows: list) -> None:
    """Ranked evidence beneath the instrument.

    A table, not a second chart: once the dominant instrument has answered
    the shape of the question, the follow-up is "by how much", and exact
    figures answer that better than a second set of bars.
    """
    head = "".join(
        f'<th class="num">{escape(h)}</th>' if i else f"<th>{escape(h)}</th>"
        for i, h in enumerate(headers)
    )
    st.markdown(
        '<div class="tl-form-card"><div class="tl-table-wrap">'
        f'<table class="tl-table"><thead><tr>{head}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div></div>',
        unsafe_allow_html=True,
    )


def _readout(title: str, body: str, evidence: str, limitation=None) -> None:
    """The panel's closing sentence: what changed, and what it rests on."""
    st.markdown(
        render_editorial_readout(
            title,
            body,
            EvidenceItem(
                evidence=evidence,
                sample=f"n={len(df)} · {start_date} → {end_date}",
                confidence=(
                    "high" if len(df) >= 30 else "medium" if len(df) >= 10 else "low"
                ),
                limitation=limitation,
            ),
        ),
        unsafe_allow_html=True,
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
        f"One {noun} so far: {row[column]}",
        f"{trades} trade{'s' if trades != 1 else ''}, {_money(total)} net. "
        f"Trade another {noun} to compare them.",
        "insights",
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
        "analytics",
        "No trades in this range yet",
        "Log a trade to unlock your analytics.",
    )
    try:
        st.page_link("pages/1_NewTrade.py", label="Log a trade →")
    except Exception:  # noqa: BLE001 — registry-less boots (AppTest) raise
        _new_trade_href = escape(
            route_href("/NewTrade", st.query_params.get("auth")), quote=True
        )
        st.markdown(
            f'<a href="{_new_trade_href}" target="_self">Log a trade →</a>',
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
    _empty("filter_alt", "No matching trades", "Adjust the date range or filters.")
    st.stop()

# One shared decision about what this sample has earned the right to show,
# so every section below agrees rather than each guessing on its own.
_state = sample_state(df)

m = compute_basic_metrics(df)
pf = compute_profit_factor_raw(df)
sess_df = by_session(df)
dow_df = by_day_of_week(df)
_sessions_comparable = enough_categories(sess_df, "session")
_dow_comparable = enough_categories(dow_df, "day_of_week")


def _pnl_cell(value) -> str:
    """One money cell, sign-coloured. Breakeven stays neutral."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return '<td class="mono num">—</td>'
    if pd.isna(v):
        return '<td class="mono num">—</td>'
    cls = " pnl-pos" if v > 0 else (" pnl-neg" if v < 0 else "")
    return f'<td class="mono num{cls}">{_money(v)}</td>'


# ══════════════════════════════════════════════════════════════════
# Lens 1 — Performance: how did this period actually go?
# ══════════════════════════════════════════════════════════════════
def _render_performance_lens(frame: pd.DataFrame) -> None:
    st.markdown(
        render_kpi_strip(
            [
                MetricItem(
                    "Net P&L",
                    _money(m["total_pnl"]),
                    detail=f"{int(m['total_trades'])} trades",
                    tone=_tone(m["total_pnl"]),
                ),
                MetricItem("Win rate", f"{m['win_rate']:.1%}"),
                MetricItem("Profit factor", _fmt_pf(pf, m["total_pnl"])),
                MetricItem(
                    "Expectancy",
                    _money(compute_expectancy(m)),
                    tone=_tone(compute_expectancy(m)),
                ),
                MetricItem(
                    "Largest win",
                    _money(m["best_trade"]) if m["wins"] else "—",
                ),
            ]
        ),
        unsafe_allow_html=True,
    )

    eq_df = equity_curve_series(frame)
    if not _state.show_series:
        render_data_state(
            "Add one more dated trade",
            "Two trading dates are needed to draw a meaningful curve.",
            "show_chart",
        )
    elif not eq_df.empty:
        _chart(
            add_sample_annotation(
                equity_curve_chart(eq_df), sample_size=len(frame), minimum=5
            ),
            "an_eq",
            "Equity curve",
            summary=(
                f"Equity curve. Cumulative profit and loss across "
                f"{len(eq_df)} trading dates, ending at "
                f"{_money(m['total_pnl'])} from {int(m['total_trades'])} trades."
            ),
        )
    else:
        _empty(
            "show_chart",
            "Equity curve not available",
            "Log P&L on trades to chart it.",
        )

    if _sessions_comparable:
        rows = []
        for r in sess_df.sort_values("total_pnl", ascending=False).itertuples(
            index=False
        ):
            rows.append(
                "<tr>"
                f"<td>{escape(str(r.session))}</td>"
                f'<td class="mono num">{int(r.trades)}</td>'
                f'<td class="mono num">{float(r.win_rate or 0.0):.1%}</td>'
                f"{_pnl_cell(r.total_pnl)}"
                "</tr>"
            )
        _ranked_table(["Session", "Trades", "Win rate", "Net P&L"], rows)

    _readout(
        "What this period recorded",
        f"{int(m['total_trades'])} trades closed at {_money(m['total_pnl'])} net, "
        f"a {m['win_rate']:.1%} win rate and {_money(compute_expectancy(m))} "
        "expected per trade.",
        f"Average win {_money(m['avg_win'])} · average loss {_money(m['avg_loss'])}",
        limitation=(
            None
            if _state.show_patterns
            else "Too few trades to read this as a pattern yet."
        ),
    )


# ══════════════════════════════════════════════════════════════════
# Lens 2 — Risk: how much was at stake, and what did it cost?
# ══════════════════════════════════════════════════════════════════
def _render_risk_lens(frame: pd.DataFrame) -> None:
    max_dd = compute_max_drawdown(compute_equity_curve(frame))
    median_rr = pd.to_numeric(frame["rr_realized"], errors="coerce").dropna().median()
    st.markdown(
        render_kpi_strip(
            [
                MetricItem("Avg R:R", _ratio(m.get("avg_rr_realized"))),
                MetricItem("Median R:R", _ratio(median_rr)),
                MetricItem(
                    "Max drawdown",
                    _money(max_dd) if _state.show_series else "—",
                    tone="negative" if _state.show_series and max_dd else "neutral",
                ),
                MetricItem("Avg win", _money(m["avg_win"]), tone="positive"),
                MetricItem(
                    "Largest loss",
                    _money(m["worst_trade"]) if m["losses"] else "—",
                ),
            ]
        ),
        unsafe_allow_html=True,
    )

    dd_df = drawdown_series(frame)
    if not _state.show_series:
        render_data_state(
            "Drawdown needs a second date",
            "A drawdown axis drawn from one trading day has no peak to fall from.",
            "trending_down",
        )
    elif not dd_df.empty:
        _chart(
            add_sample_annotation(
                drawdown_chart(dd_df), sample_size=len(frame), minimum=5
            ),
            "an_dd",
            "Drawdown",
            summary=(
                f"Drawdown. Distance below each running equity peak, in "
                f"dollars, in date order. Worst peak-to-trough "
                f"{_money(max_dd)}."
            ),
        )
    else:
        _empty(
            "trending_down",
            "Drawdown not available",
            "Log a few more trades to chart it.",
        )

    rc1, rc2 = st.columns(2)
    with rc1:
        # A "risk per trade" line through one repeated value is a flat rule
        # drawn at full height — it reads as a finding about behaviour
        # rather than as the constant it is.
        if not _state.show_series:
            render_data_state(
                "Risk trend needs a second date",
                "A trend over time needs at least two trading dates.",
                "straighten",
            )
        elif not frame["risk_amount"].notna().any():
            _empty("straighten", "Risk trend not available", "Log Risk ($) to unlock.")
        elif not has_variation(frame["risk_amount"]):
            _fixed = pd.to_numeric(frame["risk_amount"], errors="coerce").dropna()
            render_data_state(
                f"Risk is fixed at {_money(_fixed.iloc[0])}",
                "Every logged trade risked the same amount, so there is no "
                "trend to plot — which is what consistent sizing looks like.",
                "straighten",
            )
        else:
            _chart(
                risk_over_time_chart(frame),
                "an_risk",
                "Risk ($) per trade",
                summary=(
                    "Risk per trade. Dollars committed on each trade, in date "
                    "order, so sizing that drifts is visible as a trend rather "
                    "than a single number."
                ),
                compact=True,
            )
    with rc2:
        followed = pd.to_numeric(frame.get("followed_rules"), errors="coerce")
        win, _loss_mask, _be_mask = outcome_masks(frame)
        foll_mask, broke_mask = followed == 1, followed == 0
        foll_n, broke_n = int(foll_mask.sum()), int(broke_mask.sum())
        if not (foll_n or broke_n):
            _empty(
                "straighten",
                "Rule data not available",
                "Answer 'Followed your rules?' when logging to see this.",
            )
        elif not (foll_n and broke_n):
            _kept = "followed" if foll_n else "broke"
            render_data_state(
                "Nothing to compare yet",
                f"Every logged trade so far {_kept} your rules. The comparison "
                "appears once both cases exist.",
                "straighten",
            )
        else:
            _chart(
                win_rate_rules_chart(
                    float(win[foll_mask].mean()),
                    float(win[broke_mask].mean()),
                    foll_n,
                    broke_n,
                ),
                "an_rules",
                "Win rate — rules followed vs broken",
                summary=(
                    "Win rate with rules followed versus broken. "
                    f"{float(win[foll_mask].mean()):.1%} across {foll_n} "
                    f"trades that followed the rules, "
                    f"{float(win[broke_mask].mean()):.1%} across {broke_n} "
                    "that broke them."
                ),
                compact=True,
            )

    _readout(
        "What risk looked like",
        f"Worst peak-to-trough was {_money(max_dd)} against an average "
        f"{_ratio(m.get('avg_rr_realized'))} realised R.",
        f"Max drawdown {_money(max_dd)} · avg loss {_money(m['avg_loss'])}",
        limitation=(
            None
            if _state.show_series
            else "One trading date only, so drawdown has nothing to measure from."
        ),
    )


# ══════════════════════════════════════════════════════════════════
# Lens 3 — Timing: when does the edge show up?
# ══════════════════════════════════════════════════════════════════
def _render_timing_lens(frame: pd.DataFrame) -> None:
    best = sess_df.loc[sess_df["total_pnl"].idxmax()] if not sess_df.empty else None
    worst = sess_df.loc[sess_df["total_pnl"].idxmin()] if not sess_df.empty else None
    best_day = dow_df.loc[dow_df["total_pnl"].idxmax()] if not dow_df.empty else None
    st.markdown(
        render_kpi_strip(
            [
                MetricItem(
                    "Strongest session" if _sessions_comparable else "Only session",
                    str(best["session"]) if best is not None else "—",
                    detail=_money(best["total_pnl"]) if best is not None else None,
                    tone=_tone(best["total_pnl"]) if best is not None else "neutral",
                ),
                MetricItem(
                    "Lowest session",
                    (
                        str(worst["session"])
                        if worst is not None and _sessions_comparable
                        else "—"
                    ),
                    detail=(
                        _money(worst["total_pnl"])
                        if worst is not None and _sessions_comparable
                        else None
                    ),
                ),
                MetricItem(
                    "Strongest day" if _dow_comparable else "Only day",
                    str(best_day["day_of_week"]) if best_day is not None else "—",
                    detail=(
                        _money(best_day["total_pnl"]) if best_day is not None else None
                    ),
                ),
                MetricItem("Sessions traded", str(int(len(sess_df)))),
            ]
        ),
        unsafe_allow_html=True,
    )

    # A heatmap of a single cell is a coloured square, not a pattern.
    if _sessions_comparable and _dow_comparable:
        _chart(
            add_sample_annotation(
                session_dow_heatmap(frame), sample_size=len(frame), minimum=5
            ),
            "an_heat",
            "Net P&L — session × day of week",
            summary=(
                "Net profit and loss by session against day of week, as a "
                f"grid of {int(len(sess_df))} sessions by {int(len(dow_df))} "
                "weekdays. Each cell carries a plus, minus or equals sign "
                "beside its amount, and the ranked day table below this chart "
                "lists the same weekday figures as text."
            ),
        )
    else:
        render_data_state(
            "Heatmap needs more spread",
            "Trade across at least two sessions and two days to fill this grid.",
            "calendar_month",
        )

    ts1, ts2 = st.columns(2)
    with ts1:
        if sess_df.empty:
            _empty(
                "schedule",
                "Session data not available",
                "Sessions are auto-detected from entry time on new trades.",
            )
        elif not _sessions_comparable:
            _one_category_note(sess_df, "session", "session")
        else:
            _chart(
                pnl_by_session_chart(sess_df),
                "an_sess",
                "P&L by session",
                summary=(
                    "Net profit and loss by session across "
                    f"{int(len(sess_df))} sessions, highest first: "
                    + ", ".join(
                        f"{r.session} {_money(r.total_pnl)}"
                        for r in sess_df.sort_values(
                            "total_pnl", ascending=False
                        ).itertuples(index=False)
                    )
                    + "."
                ),
                compact=True,
            )
    with ts2:
        if dow_df.empty:
            _empty(
                "calendar_month",
                "Day-of-week data not available",
                "Log more trades to see day-of-week trends.",
            )
        elif not _dow_comparable:
            _one_category_note(dow_df, "day_of_week", "day")
        else:
            _chart(
                pnl_by_dow_chart(dow_df),
                "an_dow",
                "P&L by day of week",
                summary=(
                    "Net profit and loss by weekday across "
                    f"{int(len(dow_df))} weekdays. The ranked day table below "
                    "lists the same figures as text."
                ),
                compact=True,
            )

    if _dow_comparable:
        rows = []
        for r in dow_df.sort_values("total_pnl", ascending=False).itertuples(
            index=False
        ):
            rows.append(
                "<tr>"
                f"<td>{escape(str(r.day_of_week))}</td>"
                f'<td class="mono num">{int(r.trades)}</td>'
                f'<td class="mono num">{float(r.win_rate or 0.0):.1%}</td>'
                f"{_pnl_cell(r.total_pnl)}"
                "</tr>"
            )
        _ranked_table(["Day", "Trades", "Win rate", "Net P&L"], rows)

    st.markdown(
        render_section_header(
            "Daily P&L",
            "One month at a time — the range above still governs everything else "
            "on this lens.",
        ),
        unsafe_allow_html=True,
    )
    # The one full-calendar component, the same one the Journal mounts. This
    # page used to carry a second implementation whose day tint was the brand
    # teal — the colour reserved for actions — for a money-positive day.
    with st.container(key="tl_full_calendar"):
        render_trade_calendar(frame, show_month_summary=True)

    _readout(
        "When the edge showed up",
        (
            (
                f"{best['session']} carried the strongest net result at "
                f"{_money(best['total_pnl'])}."
                if _sessions_comparable
                # One session is not a winner. Say what was recorded.
                else f"Every trade in range was in {best['session']}, "
                f"netting {_money(best['total_pnl'])}."
            )
            if best is not None
            else "No session data has been recorded for this range yet."
        ),
        f"{int(len(sess_df))} session(s) · {int(len(dow_df))} weekday(s) traded",
        limitation=(
            None
            if _sessions_comparable
            else "Only one session is represented, so there is nothing to "
            "compare it against."
        ),
    )


# ══════════════════════════════════════════════════════════════════
# Lens 4 — Setups: which setups carry the edge?
# ══════════════════════════════════════════════════════════════════
def _render_setups_lens(frame: pd.DataFrame) -> None:
    setup_df = compute_breakdown(frame, "setup_type")
    # "Strongest" implies a field to have been strongest of. With one setup
    # in range there is nothing it beat, so the label states what it is.
    _setups_comparable = enough_categories(setup_df, "setup_type")
    best_setup = (
        setup_df.iloc[0] if not setup_df.empty and _state.show_patterns else None
    )
    st.markdown(
        render_kpi_strip(
            [
                MetricItem("Setups traded", str(int(len(setup_df)))),
                MetricItem(
                    "Strongest setup" if _setups_comparable else "Only setup",
                    str(best_setup["setup_type"]) if best_setup is not None else "—",
                    detail=(
                        _money(best_setup["total_pnl"])
                        if best_setup is not None
                        else None
                    ),
                    tone=(
                        _tone(best_setup["total_pnl"])
                        if best_setup is not None
                        else "neutral"
                    ),
                ),
                MetricItem("Win rate", f"{m['win_rate']:.1%}"),
                MetricItem("Profit factor", _fmt_pf(pf, m["total_pnl"])),
            ]
        ),
        unsafe_allow_html=True,
    )

    if setup_df.empty:
        _empty(
            "extension",
            "Setup data not available",
            "Assign setup types to trades to see this leaderboard.",
        )
    elif not _state.show_patterns:
        render_data_state(
            f"{trades_needed(_state, 5)} more trades to rank setups",
            "Ranking setups on a handful of trades mostly ranks luck.",
            "extension",
        )
    else:
        # compute_breakdown returns rows sorted by total_pnl desc → rank order.
        rows = []
        for rank, r in enumerate(setup_df.itertuples(index=False), start=1):
            setup_pf = compute_profit_factor_raw(
                frame[frame["setup_type"] == r.setup_type]
            )
            wr = float(r.win_rate or 0.0)
            rows.append(
                "<tr>"
                f'<td class="mono">{rank}</td>'
                f"<td>{escape(str(r.setup_type))}</td>"
                f'<td class="mono num">{int(r.trades)}</td>'
                f'<td class="mono num{" pnl-pos" if wr >= 0.5 else ""}">{wr:.1%}</td>'
                f"{_pnl_cell(r.avg_pnl)}"
                f'<td class="mono num">{_fmt_pf(setup_pf, r.total_pnl)}</td>'
                "</tr>"
            )
        _ranked_table(["Rank", "Setup", "Trades", "Win rate", "Avg P&L", "PF"], rows)

    emo_df = compute_breakdown(frame, "emotions_before")
    if emo_df.empty:
        _empty(
            "psychology", "Emotion data not available", "Fill Reflection when logging."
        )
    elif not enough_categories(emo_df, "emotions_before"):
        _one_category_note(emo_df, "emotions_before", "emotional state")
    else:
        _chart(
            pnl_by_emotion_chart(emo_df),
            "an_emo",
            "P&L by emotional state going in",
            summary=(
                "Net profit and loss by the emotional state recorded before "
                f"entry, across {int(len(emo_df))} states, highest first: "
                + ", ".join(
                    f"{r.emotions_before} {_money(r.total_pnl)}"
                    for r in emo_df.itertuples(index=False)
                )
                + "."
            ),
            compact=True,
        )

    _readout(
        "Which setups carried it",
        (
            (
                f"{best_setup['setup_type']} led on net P&L at "
                f"{_money(best_setup['total_pnl'])} across "
                f"{int(best_setup['trades'])} trades."
                if _setups_comparable
                else f"Only {best_setup['setup_type']} was traded in range, "
                f"netting {_money(best_setup['total_pnl'])} across "
                f"{int(best_setup['trades'])} trades."
            )
            if best_setup is not None
            else "Not enough trades yet to rank one setup above another."
        ),
        f"{int(len(setup_df))} setup(s) recorded in this range",
        limitation=(
            "Only one setup is represented, so there is nothing to rank it " "against."
            if _setups_comparable is False and best_setup is not None
            else (
                None
                if _state.show_patterns
                else "Ranking setups on a handful of trades mostly ranks luck."
            )
        ),
    )


# ══════════════════════════════════════════════════════════════════
# Lens selector, then the active panel
# ══════════════════════════════════════════════════════════════════
_LENS_BODIES = {
    "Performance": _render_performance_lens,
    "Risk": _render_risk_lens,
    "Timing": _render_timing_lens,
    "Setups": _render_setups_lens,
}

# The lens lives in a plain key, separate from the selector's own widget
# key: Streamlit raises on any write to a widget's key after that widget is
# instantiated, and the Journal already paid for that lesson.
_default_lens = st.session_state.get(_LENS_KEY, ANALYTICS_LENSES[0])
if _default_lens not in ANALYTICS_LENSES:
    _default_lens = ANALYTICS_LENSES[0]

lens = (
    st.radio(
        "Analytics lens",
        ANALYTICS_LENSES,
        index=ANALYTICS_LENSES.index(_default_lens),
        horizontal=True,
        key=_LENS_WIDGET_KEY,
        label_visibility="collapsed",
    )
    or _default_lens
)
st.session_state[_LENS_KEY] = lens

st.markdown(render_section_header(lens, _LENS_QUESTIONS[lens]), unsafe_allow_html=True)
_LENS_BODIES[lens](df)
