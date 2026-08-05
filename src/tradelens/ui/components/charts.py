import calendar as _calendar
import math
from typing import Optional

import pandas as pd
import plotly.graph_objects as go

from src.tradelens.ui.design_system import (
    PLOTLY_TEMPLATE,
    TL_SURFACE_CHART,
    TL_FONT_MONO,
    TL_DANGER,
    TL_DANGER_DIM,
    TL_PRIMARY,
    TL_PRIMARY_DIM,
    TL_SUCCESS,
    TL_SUCCESS_DIM,
    TL_SURFACE_ELEVATED,
    TL_CONTENT_PRIMARY,
    TL_CONTENT_SECONDARY,
    TL_WARNING,
    TL_WARNING_DIM,
)

# Chart color semantics (design-system tokens — single source of truth):
# teal = brand, reserved for trajectory lines (equity, risk) and the gauge
# bar; green/red = positive/negative outcomes, matching the KPI cards and
# table pnl-pos/pnl-neg colors; secondary content = neutral series
# (breakevens) and the dashed $0 / median reference lines.
#
# The old palette had two greys here — muted and faint, one step apart. The
# role system has one secondary content colour, so both now resolve to it.
# That is the intended collapse, not an oversight: two greys that differed by
# a hair were carrying no information a reader could actually use.
_TEAL = TL_PRIMARY
_POS = TL_SUCCESS
_NEG = TL_DANGER
_GRAY = TL_CONTENT_SECONDARY
_TEAL_FILL = TL_PRIMARY_DIM
_NEG_FILL = TL_DANGER_DIM
_REF_LINE = TL_CONTENT_SECONDARY

# The dark chart stage, restated explicitly rather than left to the
# template. Verified in the browser on streamlit==1.50.0: the frontend
# injects the app theme's backgroundColor/secondaryBackgroundColor/textColor
# into every figure's layout as EXPLICIT values, and an explicit value beats
# a template one — so with the workspace light, a template-only stage
# resolved to paper #F3F6F6 / plot #FFFFFF and put the bright mark ramp on
# near-white. `theme=None` at the call site stops the template swap; these
# keys are what survive the colour injection. Values stay tokenised, so the
# template and the layout cannot drift apart.
#
# `template` is pinned here too, rather than left to pio.templates.default.
# The global default is process state: whoever imported last wins, a test that
# swaps it leaks into the next one, and Streamlit is free to set its own. A
# figure that carries its own template is correct no matter what the global
# says — which is the difference between a chart that is right and a chart
# that happens to be right.
# hovermode is NOT set here — each chart picks the appropriate mode.
_BASE_LAYOUT = dict(
    margin=dict(l=0, r=0, t=32, b=0),
    template=PLOTLY_TEMPLATE,
    plot_bgcolor=TL_SURFACE_CHART,
    paper_bgcolor=TL_SURFACE_CHART,
    font=dict(color=TL_CONTENT_PRIMARY),
    showlegend=False,
)


# One dominant instrument per panel, one supporting height for everything
# else. Naming them here is what stops a new chart arriving at a fourth size.
_STAGE_HEIGHT = 360
_STAGE_HEIGHT_COMPACT = 240

# The sample caption hangs below the plot area. The offset is in paper
# units; the margin is the pixel band that keeps it inside the stage.
_SAMPLE_OFFSET = 0.10
_SAMPLE_MARGIN = 48


def apply_chart_stage(fig, *, title: Optional[str] = None, compact: bool = False):
    """Frame a figure as an instrument on its own stage.

    Every Plotly figure on an analytical surface goes through here, so grid,
    typography, margins, background and height come from one place rather
    than from whichever call site drew the chart. Mutates and returns the
    same figure, so it composes: ``apply_chart_stage(build(df))``.

    Two things are pinned rather than inherited. The backgrounds are set
    explicitly because Streamlit's frontend injects the app theme's colours
    into every figure as EXPLICIT layout values, and an explicit value beats a
    template one. The template itself is set explicitly because
    pio.templates.default is process-wide mutable state — import order, a test
    that swaps it, or Streamlit itself can change what a figure resolves
    against.
    """
    # Never shrink a bottom margin another helper already reserved:
    # add_sample_annotation books space for its caption, and the two may be
    # applied in either order.
    existing_bottom = getattr(fig.layout.margin, "b", None) or 0
    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        paper_bgcolor=TL_SURFACE_CHART,
        plot_bgcolor=TL_SURFACE_CHART,
        font=dict(color=TL_CONTENT_PRIMARY),
        height=_STAGE_HEIGHT_COMPACT if compact else _STAGE_HEIGHT,
        margin=dict(l=8, r=8, t=32 if title else 8, b=max(8, existing_bottom)),
    )
    # automargin: the stage has a visible edge, so pinned margins clip the
    # tick labels against it.
    fig.update_xaxes(automargin=True)
    fig.update_yaxes(automargin=True)
    if title:
        fig.update_layout(title=dict(text=title))
    return fig


def add_sample_annotation(fig, *, sample_size: int, minimum: int):
    """State on the chart itself what it was drawn from.

    A reader who scrolled straight to a chart never saw the panel's caveat,
    so the sample travels with the figure. Below the threshold it says the
    sample is small — an unqualified chart of four trades reads as a
    finding.
    """
    noun = "trade" if sample_size == 1 else "trades"
    text = f"n={sample_size} {noun}"
    if sample_size < minimum:
        text += f" · small sample, {minimum} needed to read a pattern"
    # The caption sits BELOW the plot area, so it needs room reserved in the
    # bottom margin. Without it Plotly draws the text outside the figure's
    # painted region and the stage clips it — measured in the browser.
    fig.add_annotation(
        text=text,
        xref="paper",
        yref="paper",
        x=1.0,
        y=-_SAMPLE_OFFSET,
        xanchor="right",
        yanchor="top",
        showarrow=False,
        font=dict(family=TL_FONT_MONO, size=11, color=TL_CONTENT_SECONDARY),
    )
    existing_bottom = getattr(fig.layout.margin, "b", None) or 0
    fig.update_layout(margin_b=max(existing_bottom, _SAMPLE_MARGIN))
    return fig


def _empty_figure(message: str = "No trades in this period yet.") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font=dict(size=14, color=_GRAY),
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
        line_color=_REF_LINE,
        line_width=1,
    )
    fig.update_layout(
        **_BASE_LAYOUT,
        hovermode="x unified",
        # Force clean YYYY-MM-DD ticks — never microsecond timestamps.
        xaxis=dict(showgrid=False, title=None, type="date", tickformat="%Y-%m-%d"),
        yaxis=dict(
            showgrid=True,
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
            line=dict(color=_NEG, width=1.5),
            fillcolor=_NEG_FILL,
            hovertemplate="Date: %{x}<br>Drawdown: $%{y:,.2f}<extra></extra>",
        )
    )
    fig.add_hline(y=0, line_dash="dash", line_color=_REF_LINE, line_width=1)
    fig.update_layout(
        **_BASE_LAYOUT,
        hovermode="x unified",
        xaxis=dict(showgrid=False, title=None),
        yaxis=dict(
            showgrid=True,
            title=None,
            tickprefix="$",
        ),
    )
    return fig


def win_rate_by_dow_chart(df: pd.DataFrame) -> go.Figure:
    """
    Win rate per day of week (vertical bars).

    Input: by_day_of_week() output — columns include day_of_week, win_rate, total_pnl.
    The worst day (lowest win_rate) is highlighted in danger red; others neutral gray.
    """
    if df is None or df.empty:
        return _empty_figure()

    days = [str(d) for d in df["day_of_week"]]
    win_rates = df["win_rate"].tolist()
    total_pnls = df["total_pnl"].tolist()
    trades = df["trades"].tolist()

    worst_idx = int(df["win_rate"].idxmin())
    colors = [_NEG if i == worst_idx else _GRAY for i in range(len(df))]

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
        ),
        xaxis=dict(title=None),
    )
    return fig


def pnl_by_strategy_chart(df: pd.DataFrame) -> go.Figure:
    """
    Total P/L per strategy (horizontal bars).

    Input: by_strategy() output — columns: strategy_used, total_pnl, profit_factor, trades.
    Positive bars green, negative red. profit_factor displayed as "∞" when inf.
    """
    if df is None or df.empty:
        return _empty_figure()

    colors = [_POS if v >= 0 else _NEG for v in df["total_pnl"]]
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
    Color bands: red [0–1.0], amber [1.0–1.5], green [1.5–3.0]; brand-teal bar.
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
                    {"range": [0, 1.0], "color": TL_DANGER_DIM},
                    {"range": [1.0, 1.5], "color": TL_WARNING_DIM},
                    {"range": [1.5, 3.0], "color": TL_SUCCESS_DIM},
                ],
                "threshold": {
                    "line": {"color": TL_WARNING, "width": 2},
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
    Positive-bin bars green, negative-bin bars red.
    Optional median_rr draws a vertical reference line.
    """
    if df is None or df.empty:
        return _empty_figure()

    mid = (df["bin_left"] + df["bin_right"]) / 2
    colors = [_POS if m >= 0 else _NEG for m in mid]
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
            line_color=_REF_LINE,
            line_width=1.5,
            annotation_text=f"Median: {median_rr:.2f}R",
            annotation_position="top right",
            annotation_font_size=11,
        )

    fig.update_layout(
        **_BASE_LAYOUT,
        hovermode="closest",
        xaxis=dict(title="R Multiple", ticksuffix="R"),
        yaxis=dict(title="Trades"),
        bargap=0.05,
    )
    return fig


def emotion_vs_rr_chart(df: pd.DataFrame) -> go.Figure:
    """
    Average R-multiple per emotional state (horizontal bars).

    Input: emotion_vs_rr() output — columns: emotions_before, trades, avg_rr_realized.
    Positive avg_rr green, negative red.
    """
    if df is None or df.empty:
        return _empty_figure()

    colors = [_POS if v >= 0 else _NEG for v in df["avg_rr_realized"]]

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
            marker_color=_POS,
            hovertemplate="Setup: %{y}<br>Wins: %{x}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            y=df["setup_type"],
            x=df["losses"],
            name="Losses",
            orientation="h",
            marker_color=_NEG,
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
    """Vertical P&L bar chart — positive green, negative red (shared helper)."""
    colors = [_POS if float(v) >= 0 else _NEG for v in values]
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
        yaxis=dict(title=None, tickprefix="$"),
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
    colors = [_POS if float(v) >= 0 else _NEG for v in df["total_pnl"]]
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
        yaxis=dict(title=None, tickprefix="$"),
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
            marker_color=[_POS, _NEG],
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
        yaxis=dict(tickformat=".0%", title=None),
    )
    return fig


def session_dow_heatmap(df: pd.DataFrame) -> go.Figure:
    """Net P&L heatmap across session (rows) × day of week (cols).

    Stands in for a "time of day" heatmap using the session bucket, since the
    entry hour is not stored. Red→green diverging scale centered at $0.
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
            colorscale=[[0.0, _NEG], [0.5, TL_SURFACE_ELEVATED], [1.0, _POS]],
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
            colorscale=[[0.0, _NEG], [0.5, TL_SURFACE_ELEVATED], [1.0, _POS]],
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
