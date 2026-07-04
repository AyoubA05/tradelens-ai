"""
Compact monthly trade calendar for the Dashboard (Item 12).

Each day the trader traded shows a colored dot — 🟢 net-positive day, 🔴
net-negative, ⚪ breakeven — matching the result badges already used on the
Journal page. Clicking a day opens a mini-panel listing that day's trades.
Pure helpers are Streamlit-free; rendering imports Streamlit lazily.
"""

from __future__ import annotations

import calendar as _cal
import datetime

_DOTS = {"positive": "🟢", "negative": "🔴", "breakeven": "⚪"}
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_SELECTED_KEY = "dash_cal_day"


def month_options(daily: dict) -> list:
    """Distinct 'YYYY-MM' months present in the daily map, newest first."""
    return sorted({d[:7] for d in daily}, reverse=True)


def month_label(ym: str) -> str:
    """'2026-07' → 'July 2026' (falls back to the raw string on junk)."""
    try:
        year, month = ym.split("-")
        return f"{_cal.month_name[int(month)]} {year}"
    except (ValueError, IndexError):
        return ym


def day_key(year: int, month: int, day: int) -> str:
    return f"{year:04d}-{month:02d}-{day:02d}"


def render_trade_calendar(df) -> None:
    """Render the monthly calendar + click-to-open day panel for `df` trades."""
    import streamlit as st

    from src.tradelens.services.metrics import daily_outcomes

    daily = daily_outcomes(df)
    if not daily:
        st.caption("No dated trades yet — the calendar fills in as you log.")
        return

    months = month_options(daily)
    picked = st.selectbox(
        "Month",
        months,
        format_func=month_label,
        key="dash_cal_month",
        label_visibility="collapsed",
    )
    try:
        year, month = (int(p) for p in picked.split("-"))
    except (ValueError, AttributeError):
        year, month = datetime.date.today().year, datetime.date.today().month

    header = st.columns(7)
    for i, name in enumerate(_WEEKDAYS):
        header[i].caption(name)

    for week in _cal.monthcalendar(year, month):
        cols = st.columns(7)
        for i, day in enumerate(week):
            if day == 0:
                cols[i].markdown("&nbsp;", unsafe_allow_html=True)
                continue
            key = day_key(year, month, day)
            info = daily.get(key)
            if info:
                dot = _DOTS.get(info["outcome"], "⚪")
                if cols[i].button(
                    f"{dot} {day}",
                    key=f"dash_cal_{key}",
                    use_container_width=True,
                    help=f"{info['trades']} trade(s) · net ${info['pnl']:,.2f}",
                ):
                    st.session_state[_SELECTED_KEY] = key
            else:
                cols[i].markdown(
                    f"<div style='text-align:center;opacity:0.45'>{day}</div>",
                    unsafe_allow_html=True,
                )

    st.caption("🟢 net positive day · 🔴 net negative · ⚪ breakeven — click a day")

    selected = st.session_state.get(_SELECTED_KEY)
    if selected and selected in daily:
        info = daily[selected]
        st.markdown(
            f"**{selected}** — {info['trades']} trade(s) · net ${info['pnl']:,.2f}"
        )
        day_df = df[df["trade_date"] == selected]
        show_cols = [
            c
            for c in ("asset", "direction", "setup_type", "result", "pnl")
            if c in day_df.columns
        ]
        st.dataframe(
            day_df[show_cols].rename(
                columns={
                    "asset": "Asset",
                    "direction": "Direction",
                    "setup_type": "Setup",
                    "result": "Result",
                    "pnl": "P&L ($)",
                }
            ),
            hide_index=True,
            use_container_width=True,
        )
        if st.button("Close day view", key="dash_cal_close"):
            st.session_state.pop(_SELECTED_KEY, None)
            st.rerun()
