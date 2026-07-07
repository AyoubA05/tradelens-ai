import calendar as _calendar
import math
from typing import Optional

import pandas as pd
import plotly.graph_objects as go

from src.tradelens.ui.components.theme import TEAL, TERRA

# Brand colors come from the design system (single source of truth).
_TEAL = TEAL
_RED = TERRA
_GRAY = "#8E9196"
_TEAL_FILL = "rgba(32, 128, 141, 0.15)"
_RED_FILL = "rgba(168, 75, 47, 0.15)"

# Transparent backgrounds so charts adapt to Streamlit light/dark themes.
# hovermode is NOT set here — each chart picks the appropriate mode.
_BASE_LAYOUT = dict(
    margin=dict(l=0, r=0, t=32, b=0),
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    showlegend=False,
)


def _empty_figure(message: str = "No trades in this period yet.") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font=dict(size=14, color="#888888"),
    )
    fig.update_layout(
        **_BASE_LAYOUT,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )
    return fig


def equity_curve_chart(df: pd.DataFrame) -> go.Figure:
    """
    Cumulative P/L over time (line + area fill).

    Input: equity_curve_series() output — columns: trade_date, pnl, cumulative_pnl.
    """
    if df is None or df.empty:
        return _empty_figure()

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["trade_date"],
            y=df["cumulative_pnl"],
            mode="lines",
            fill="tozeroy",
            line=dict(color=_TEAL, width=2),
            fillcolor=_TEAL_FILL,
            hovertemplate="Date: %{x}<br>Cumulative P/L: $%{y:,.2f}<extra></extra>",
        )
    )
    fig.add_hline(
        y=0,
        line_dash="dash",
        line_color="rgba(128, 128, 128, 0.5)",
        line_width=1,
    )
    fig.update_layout(
        **_BASE_LAYOUT,
        hovermode="x unified",
        # Force clean YYYY-MM-DD ticks — never microsecond timestamps.
        xaxis=dict(showgrid=False, title=None, type="date", tickformat="%Y-%m-%d"),
        yaxis=dict(
            showgrid=True,
            gridcolor="rgba(128, 128, 128, 0.2)",
            title=None,
            tickprefix="$",
        ),
    )
    return fig


def drawdown_chart(df: pd.DataFrame) -> go.Figure:
    """
    Per-trade drawdown series (red area chart, negative values).

    Input: drawdown_series() output — columns: trade_date, cumulative_pnl,
    running_peak, drawdown.
    """
    if df is None or df.empty:
        return _empty_figure()

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["trade_date"],
            y=df["drawdown"],
            mode="lines",
            fill="tozeroy",
            line=dict(color=_RED, width=1.5),
            fillcolor=_RED_FILL,
            hovertemplate="Date: %{x}<br>Drawdown: $%{y:,.2f}<extra></extra>",
        )
    )
    fig.add_hline(
        y=0, line_dash="dash", line_color="rgba(128, 128, 128, 0.5)", line_width=1
    )
    fig.update_layout(
        **_BASE_LAYOUT,
        hovermode="x unified",
        xaxis=dict(showgrid=False, title=None),
        yaxis=dict(
            showgrid=True,
            gridcolor="rgba(128, 128, 128, 0.2)",
            title=None,
            tickprefix="$",
        ),
    )
    return fig


def win_rate_by_dow_chart(df: pd.DataFrame) -> go.Figure:
    """
    Win rate per day of week (vertical bars).

    Input: by_day_of_week() output — columns include day_of_week, win_rate, total_pnl.
    The worst day (lowest win_rate) is highlighted in terra red; others neutral gray.
    """
    if df is None or df.empty:
        return _empty_figure()

    days = [str(d) for d in df["day_of_week"]]
    win_rates = df["win_rate"].tolist()
    total_pnls = df["total_pnl"].tolist()
    trades = df["trades"].tolist()

    worst_idx = int(df["win_rate"].idxmin())
    colors = [_RED if i == worst_idx else _GRAY for i in range(len(df))]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=days,
            y=win_rates,
            marker_color=colors,
            customdata=list(zip(total_pnls, trades)),
            hovertemplate=(
                "Day: %{x}<br>"
                "Win Rate: %{y:.1%}<br>"
                "Total P/L: $%{customdata[0]:,.2f}<br>"
                "Trades: %{customdata[1]}<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        **_BASE_LAYOUT,
        hovermode="closest",
        yaxis=dict(
            tickformat=".0%",
            title=None,
            gridcolor="rgba(128, 128, 128, 0.2)",
        ),
        xaxis=dict(title=None),
    )
    return fig


def pnl_by_strategy_chart(df: pd.DataFrame) -> go.Figure:
    """
    Total P/L per strategy (horizontal bars).

    Input: by_strategy() output — columns: strategy_used, total_pnl, profit_factor, trades.
    Positive bars teal, negative terra red. profit_factor displayed as "∞" when inf.
    """
    if df is None or df.empty:
        return _empty_figure()

    colors = [_TEAL if v >= 0 else _RED for v in df["total_pnl"]]
    pf_labels = [
        "∞" if math.isinf(float(v)) else f"{v:.2f}" for v in df["profit_factor"]
    ]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=df["strategy_used"],
            x=df["total_pnl"],
            orientation="h",
            marker_color=colors,
            customdata=list(zip(df["trades"].tolist(), pf_labels)),
            hovertemplate=(
                "Strategy: %{y}<br>"
                "Total P/L: $%{x:,.2f}<br>"
                "Trades: %{customdata[0]}<br>"
                "Profit Factor: %{customdata[1]}<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        **_BASE_LAYOUT,
        hovermode="closest",
        xaxis=dict(title=None, tickprefix="$"),
        yaxis=dict(title=None, autorange="reversed"),
    )
    return fig


def profit_factor_gauge(value: float) -> go.Figure:
    """
    Indicator gauge showing profit factor on a 0–3 scale.

    Input: float from compute_profit_factor_raw(). inf is capped at 3.0 for
    display; the title shows "(∞)" when infinite. Reference line at 1.5.
    Color bands: red [0–1.0], yellow [1.0–1.5], teal [1.5–3.0].
    """
    if math.isnan(value) if isinstance(value, float) else False:
        display_val = 0.0
    elif math.isinf(value):
        display_val = 3.0
    else:
        display_val = max(0.0, min(float(value), 3.0))

    inf_note = " (∞)" if math.isinf(value) else ""
    title_text = f"Profit Factor{inf_note}"

    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=display_val,
            title={"text": title_text, "font": {"size": 14}},
            number={"valueformat": ".2f"},
            gauge={
                "axis": {"range": [0, 3], "tickwidth": 1},
                "bar": {"color": _TEAL, "thickness": 0.25},
                "bgcolor": "rgba(0,0,0,0)",
                "steps": [
                    {"range": [0, 1.0], "color": "rgba(168, 75, 47, 0.2)"},
                    {"range": [1.0, 1.5], "color": "rgba(255, 180, 0, 0.2)"},
                    {"range": [1.5, 3.0], "color": "rgba(32, 128, 141, 0.2)"},
                ],
                "threshold": {
                    "line": {"color": "orange", "width": 2},
                    "thickness": 0.75,
                    "value": 1.5,
                },
            },
        )
    )
    fig.update_layout(
        **{**_BASE_LAYOUT, "margin": dict(l=20, r=20, t=40, b=20), "height": 250}
    )
    return fig


def r_multiple_histogram(
    df: pd.DataFrame,
    median_rr: Optional[float] = None,
) -> go.Figure:
    """
    Pre-binned R-multiple histogram (not go.Histogram — data is already binned).

    Input: r_multiple_distribution() output — columns: bin_left, bin_right, count.
    Positive-bin bars teal, negative-bin bars terra red.
    Optional median_rr draws a vertical reference line.
    """
    if df is None or df.empty:
        return _empty_figure()

    mid = (df["bin_left"] + df["bin_right"]) / 2
    colors = [_TEAL if m >= 0 else _RED for m in mid]
    widths = (df["bin_right"] - df["bin_left"]).tolist()

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=mid,
            y=df["count"],
            width=widths,
            marker_color=colors,
            customdata=list(zip(df["bin_left"].tolist(), df["bin_right"].tolist())),
            hovertemplate=(
                "R Range: [%{customdata[0]:.2f}, %{customdata[1]:.2f}]<br>"
                "Count: %{y}<extra></extra>"
            ),
        )
    )

    if median_rr is not None:
        fig.add_vline(
            x=float(median_rr),
            line_dash="dash",
            line_color=_GRAY,
            line_width=1.5,
            annotation_text=f"Median: {median_rr:.2f}R",
            annotation_position="top right",
            annotation_font_size=11,
        )

    fig.update_layout(
        **_BASE_LAYOUT,
        hovermode="closest",
        xaxis=dict(title="R Multiple", ticksuffix="R"),
        yaxis=dict(title="Trades", gridcolor="rgba(128, 128, 128, 0.2)"),
        bargap=0.05,
    )
    return fig


def emotion_vs_rr_chart(df: pd.DataFrame) -> go.Figure:
    """
    Average R-multiple per emotional state (horizontal bars).

    Input: emotion_vs_rr() output — columns: emotions_before, trades, avg_rr_realized.
    Positive avg_rr teal, negative terra red.
    """
    if df is None or df.empty:
        return _empty_figure()

    colors = [_TEAL if v >= 0 else _RED for v in df["avg_rr_realized"]]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=df["emotions_before"],
            x=df["avg_rr_realized"],
            orientation="h",
            marker_color=colors,
            customdata=df["trades"],
            hovertemplate=(
                "Emotion: %{y}<br>"
                "Avg R: %{x:.2f}R<br>"
                "Trades: %{customdata}<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        **_BASE_LAYOUT,
        hovermode="closest",
        xaxis=dict(title=None, ticksuffix="R"),
        yaxis=dict(title=None, autorange="reversed"),
    )
    return fig


def setup_breakdown_chart(df: pd.DataFrame) -> go.Figure:
    """
    Stacked horizontal bar showing win/loss/breakeven composition per setup type.

    Input: by_setup_type() output — columns: setup_type, trades, wins, losses, breakevens.
    Sorted by trades descending. Legend shown.
    """
    if df is None or df.empty:
        return _empty_figure()

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=df["setup_type"],
            x=df["wins"],
            name="Wins",
            orientation="h",
            marker_color=_TEAL,
            hovertemplate="Setup: %{y}<br>Wins: %{x}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            y=df["setup_type"],
            x=df["losses"],
            name="Losses",
            orientation="h",
            marker_color=_RED,
            hovertemplate="Setup: %{y}<br>Losses: %{x}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            y=df["setup_type"],
            x=df["breakevens"],
            name="Breakevens",
            orientation="h",
            marker_color=_GRAY,
            hovertemplate="Setup: %{y}<br>Breakevens: %{x}<extra></extra>",
        )
    )
    fig.update_layout(
        **{**_BASE_LAYOUT, "showlegend": True},
        hovermode="closest",
        barmode="stack",
        xaxis=dict(title="Trades"),
        yaxis=dict(title=None, autorange="reversed"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def _pnl_bar(labels, values, hover_label: str) -> go.Figure:
    """Vertical P&L bar chart — positive teal, negative terra (shared helper)."""
    colors = [_TEAL if float(v) >= 0 else _RED for v in values]
    fig = go.Figure(
        go.Bar(
            x=list(labels),
            y=list(values),
            marker_color=colors,
            hovertemplate=(
                f"{hover_label}: %{{x}}<br>P/L: $%{{y:,.2f}}<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        **_BASE_LAYOUT,
        hovermode="closest",
        xaxis=dict(title=None),
        yaxis=dict(title=None, tickprefix="$", gridcolor="rgba(128, 128, 128, 0.2)"),
    )
    return fig


def pnl_by_session_chart(df: pd.DataFrame) -> go.Figure:
    """Total P&L by market session. Input: compute_breakdown(df, "session")."""
    if df is None or df.empty:
        return _empty_figure("No session data yet.")
    return _pnl_bar(
        df["session"].astype(str).tolist(), df["total_pnl"].tolist(), "Session"
    )


def pnl_by_dow_chart(df: pd.DataFrame) -> go.Figure:
    """Total P&L by day of week. Input: by_day_of_week(df)."""
    if df is None or df.empty:
        return _empty_figure("No day-of-week data yet.")
    return _pnl_bar(
        [str(d) for d in df["day_of_week"]], df["total_pnl"].tolist(), "Day"
    )


def pnl_by_emotion_chart(df: pd.DataFrame) -> go.Figure:
    """Total P&L by pre-trade emotional state (horizontal bars).

    Input: compute_breakdown(df, "emotions_before") — columns include
    emotions_before, total_pnl, trades.
    """
    if df is None or df.empty:
        return _empty_figure("No emotional-state tags yet.")
    colors = [_TEAL if float(v) >= 0 else _RED for v in df["total_pnl"]]
    fig = go.Figure(
        go.Bar(
            y=df["emotions_before"].astype(str),
            x=df["total_pnl"],
            orientation="h",
            marker_color=colors,
            customdata=df["trades"],
            hovertemplate=(
                "Emotion: %{y}<br>P/L: $%{x:,.2f}<br>"
                "Trades: %{customdata}<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        **_BASE_LAYOUT,
        hovermode="closest",
        xaxis=dict(title=None, tickprefix="$"),
        yaxis=dict(title=None, autorange="reversed"),
    )
    return fig


def risk_over_time_chart(df: pd.DataFrame) -> go.Figure:
    """Risk ($) per trade over time (line + markers).

    Input: a trades DataFrame with trade_date and risk_amount columns.
    """
    if df is None or df.empty or "risk_amount" not in df.columns:
        return _empty_figure("No risk data yet.")
    work = df.dropna(subset=["risk_amount"]).copy()
    if work.empty:
        return _empty_figure("No risk data yet.")
    work = work.sort_values("trade_date")
    fig = go.Figure(
        go.Scatter(
            x=work["trade_date"],
            y=pd.to_numeric(work["risk_amount"], errors="coerce"),
            mode="lines+markers",
            line=dict(color=_TEAL, width=2),
            marker=dict(size=5, color=_TEAL),
            hovertemplate="Date: %{x}<br>Risk: $%{y:,.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        **_BASE_LAYOUT,
        hovermode="x unified",
        xaxis=dict(showgrid=False, title=None, type="date", tickformat="%Y-%m-%d"),
        yaxis=dict(title=None, tickprefix="$", gridcolor="rgba(128, 128, 128, 0.2)"),
    )
    return fig


def win_rate_rules_chart(
    followed_wr: float, broke_wr: float, followed_n: int, broke_n: int
) -> go.Figure:
    """Win rate when following rules vs. breaking them (two bars)."""
    fig = go.Figure(
        go.Bar(
            x=["Followed rules", "Broke rules"],
            y=[followed_wr, broke_wr],
            marker_color=[_TEAL, _RED],
            customdata=[followed_n, broke_n],
            hovertemplate=(
                "%{x}<br>Win rate: %{y:.1%}<br>Trades: %{customdata}<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        **_BASE_LAYOUT,
        hovermode="closest",
        xaxis=dict(title=None),
        yaxis=dict(tickformat=".0%", title=None, gridcolor="rgba(128, 128, 128, 0.2)"),
    )
    return fig


def session_dow_heatmap(df: pd.DataFrame) -> go.Figure:
    """Net P&L heatmap across session (rows) × day of week (cols).

    Stands in for a "time of day" heatmap using the session bucket, since the
    entry hour is not stored. Red→teal diverging scale centered at $0.
    """
    if (
        df is None
        or df.empty
        or "session" not in df.columns
        or "day_of_week" not in df.columns
    ):
        return _empty_figure("No session/day data yet.")
    work = df.dropna(subset=["session", "day_of_week"]).copy()
    if work.empty:
        return _empty_figure("No session/day data yet.")
    work["pnl"] = pd.to_numeric(work.get("pnl"), errors="coerce").fillna(0.0)
    piv = work.pivot_table(
        index="session",
        columns="day_of_week",
        values="pnl",
        aggfunc="sum",
        fill_value=0,
    )
    order = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    cols = [d for d in order if d in piv.columns]
    if not cols:
        return _empty_figure("No session/day data yet.")
    piv = piv[cols]
    cmax = max(float(abs(piv.values).max()), 1.0)
    fig = go.Figure(
        go.Heatmap(
            z=piv.values,
            x=[c[:3] for c in piv.columns],
            y=list(piv.index),
            colorscale=[[0.0, _RED], [0.5, "#2b2b2b"], [1.0, _TEAL]],
            zmid=0,
            zmin=-cmax,
            zmax=cmax,
            hovertemplate=(
                "Session: %{y}<br>Day: %{x}<br>P/L: $%{z:,.2f}<extra></extra>"
            ),
            xgap=3,
            ygap=3,
            colorbar=dict(title="Net $"),
        )
    )
    fig.update_layout(
        **_BASE_LAYOUT, height=320, xaxis=dict(title=None), yaxis=dict(title=None)
    )
    return fig


def calendar_heatmap_chart(daily: pd.DataFrame, year: int, month: int) -> go.Figure:
    """Month-grid heatmap of net daily P&L.

    `daily` is the output of metrics.calendar_daily_pnl (columns: day, net_pnl,
    trades). Cells are colored on a red→green diverging scale centered at $0;
    days with no trades render blank. Day number + net $ + trade count are shown
    in-cell.
    """
    pnl_by_day: dict = {}
    if daily is not None and not daily.empty:
        for _, row in daily.iterrows():
            pnl_by_day[int(row["day"])] = (float(row["net_pnl"]), int(row["trades"]))

    weeks = _calendar.monthcalendar(year, month)  # 0 marks days outside the month
    z, text = [], []
    for week in weeks:
        zr, tr = [], []
        for day in week:
            if day == 0:
                zr.append(None)
                tr.append("")
            elif day in pnl_by_day:
                pnl, trades = pnl_by_day[day]
                zr.append(pnl)
                tr.append(f"<b>{day}</b><br>${pnl:,.0f}<br>{trades}t")
            else:
                zr.append(None)
                tr.append(f"<b>{day}</b>")
        z.append(zr)
        text.append(tr)

    cmax = max([abs(v) for row in z for v in row if v is not None] or [1.0])

    fig = go.Figure(
        go.Heatmap(
            z=z,
            x=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
            y=[f"Wk {i + 1}" for i in range(len(weeks))],
            text=text,
            texttemplate="%{text}",
            textfont=dict(size=11),
            colorscale=[[0.0, _RED], [0.5, "#2b2b2b"], [1.0, _TEAL]],
            zmid=0,
            zmin=-cmax,
            zmax=cmax,
            hoverinfo="text",
            xgap=3,
            ygap=3,
            colorbar=dict(title="Net $"),
        )
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(
        **_BASE_LAYOUT,
        height=380,
        title=f"{_calendar.month_name[month]} {year}",
    )
    return fig
