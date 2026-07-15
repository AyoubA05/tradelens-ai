"""
Trader calendar (Session C, Section 6).

Renders a real month-grid calendar with HTML/CSS — not a Plotly heatmap — plus a
month-KPI row and a per-day trade drill-down. Day cells are tinted teal (net
positive), terra (net negative), or neutral. Reuses metrics.calendar_daily_pnl
for daily aggregates.
"""

from __future__ import annotations

import calendar as _calendar
import datetime as dt

import pandas as pd

from src.tradelens.services.metrics import calendar_daily_pnl
from src.tradelens.utils.format import humanize

_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_BORDER = "1px solid rgba(255,255,255,0.07)"


def _cell_html(day: int, info) -> str:
    """One calendar cell. `info` is (net_pnl, trades) or None."""
    if day == 0:
        return f'<td style="height:62px;border:{_BORDER}"></td>'
    if info is None:
        bg, body = "rgba(255,255,255,0.02)", ""
    else:
        pnl, trades = info
        if pnl > 0:
            bg = "rgba(32,128,141,0.18)"
        elif pnl < 0:
            bg = "rgba(168,75,47,0.18)"
        else:
            bg = "rgba(255,255,255,0.05)"
        sign = "-" if pnl < 0 else ""
        body = (
            f"<div style=\"font-family:'JetBrains Mono',monospace;font-size:0.8rem;"
            f'font-weight:600">{sign}${abs(pnl):,.0f}</div>'
            f'<div style="font-size:0.68rem;color:#8E9196">{trades}t</div>'
        )
    return (
        f'<td style="height:62px;vertical-align:top;padding:4px;border:{_BORDER};'
        f'background:{bg}"><div style="font-size:0.72rem;color:#B4B8BD">{day}</div>'
        f"{body}</td>"
    )


def _shift_month(delta: int) -> None:
    import streamlit as st

    y, m = st.session_state["cal_year"], st.session_state["cal_month"]
    m += delta
    if m < 1:
        m, y = 12, y - 1
    elif m > 12:
        m, y = 1, y + 1
    st.session_state["cal_year"], st.session_state["cal_month"] = y, m


def render_calendar(trades_df) -> None:
    """Render the month calendar, KPIs, grid, and day drill-down."""
    import streamlit as st

    today = dt.date.today()
    st.session_state.setdefault("cal_year", today.year)
    st.session_state.setdefault("cal_month", today.month)

    prev, title, nxt = st.columns([1, 3, 1])
    prev.button("‹ Prev", on_click=_shift_month, args=(-1,), key="cal_prev")
    nxt.button("Next ›", on_click=_shift_month, args=(1,), key="cal_next")
    year = st.session_state["cal_year"]
    month = st.session_state["cal_month"]
    title.markdown(
        f"<h3 style='text-align:center;margin:0'>{_calendar.month_name[month]} "
        f"{year}</h3>",
        unsafe_allow_html=True,
    )

    has_data = trades_df is not None and not trades_df.empty
    daily = calendar_daily_pnl(trades_df, year, month) if has_data else pd.DataFrame()

    pnl_by_day: dict = {}
    if not daily.empty:
        for _, row in daily.iterrows():
            pnl_by_day[int(row["day"])] = (float(row["net_pnl"]), int(row["trades"]))

    # ── Month KPIs ────────────────────────────────────────────────
    if not daily.empty:
        net = float(daily["net_pnl"].sum())
        n_trades = int(daily["trades"].sum())
        wins = int(daily["wins"].sum())
        win_rate = wins / n_trades if n_trades else 0.0
        best = daily.loc[daily["net_pnl"].idxmax()]
        worst = daily.loc[daily["net_pnl"].idxmin()]
        k = st.columns(5)
        k[0].metric("Month Net P&L", f"${net:,.0f}")
        k[1].metric("Trades", n_trades)
        k[2].metric("Win Rate", f"{win_rate:.0%}")
        k[3].metric(
            "Best Day", f"${best['net_pnl']:,.0f}", help=f"Day {int(best['day'])}"
        )
        k[4].metric(
            "Worst Day", f"${worst['net_pnl']:,.0f}", help=f"Day {int(worst['day'])}"
        )
    else:
        st.caption(f"No trades in {_calendar.month_name[month]} {year}.")

    # ── Grid ──────────────────────────────────────────────────────
    header = "".join(
        f'<th style="padding:4px;color:#8E9196;font-size:0.72rem;font-weight:500">'
        f"{d}</th>"
        for d in _WEEKDAYS
    )
    body = ""
    for week in _calendar.monthcalendar(year, month):
        body += (
            "<tr>"
            + "".join(_cell_html(day, pnl_by_day.get(day)) for day in week)
            + "</tr>"
        )
    st.markdown(
        '<table style="width:100%;border-collapse:collapse;table-layout:fixed">'
        f"<thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>",
        unsafe_allow_html=True,
    )

    # ── Day drill-down ────────────────────────────────────────────
    if pnl_by_day:
        st.markdown("#### Day Detail")
        days = sorted(pnl_by_day.keys())
        selected = st.selectbox(
            "View a day's trades",
            days,
            format_func=lambda d: f"{_calendar.month_name[month]} {d}, {year}",
            key="cal_day_select",
        )
        st.session_state["selected_day"] = selected
        date_prefix = f"{year:04d}-{month:02d}-{selected:02d}"
        day_trades = trades_df[
            trades_df["trade_date"].astype(str).str.startswith(date_prefix)
        ]
        if not day_trades.empty:
            # Title Case headers + $-formatted P&L, matching the Journal table.
            _headers = {
                "trade_date": "Date",
                "asset": "Asset",
                "result": "Result",
                "pnl": "P&L",
                "killzone": "Killzone",
                "setup_type": "Setup",
            }
            cols = [c for c in _headers if c in day_trades.columns]
            disp = day_trades[cols].copy()
            for col in ("killzone", "setup_type", "result"):
                if col in disp.columns:
                    disp[col] = disp[col].map(humanize)
            if "pnl" in disp.columns:
                disp["pnl"] = disp["pnl"].map(
                    lambda v: (
                        "—"
                        if v is None or pd.isna(v)
                        else (f"-${abs(v):,.2f}" if v < 0 else f"${v:,.2f}")
                    )
                )
            disp = disp.rename(columns=_headers)
            st.dataframe(disp, hide_index=True, width="stretch")
