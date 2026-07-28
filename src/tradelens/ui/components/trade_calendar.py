"""
Compact monthly trade calendar for the Dashboard (Item 12).

Each day the trader traded shows a flat design-system dot — green
net-positive, red net-negative, muted gray breakeven — matching the
outcome colors used on the Journal page and in the charts. The dot is
drawn in CSS (design_system.py): the day's outcome rides in the button
key, so the st-key-calday_… container class selects the color. Clicking
a day opens a mini-panel listing that day's trades. Pure helpers are
Streamlit-free; rendering imports Streamlit lazily.
"""

from __future__ import annotations

import calendar as _cal
import datetime

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


def compact_month_html(year: int, month: int, daily: dict) -> str:
    """A month preview as one HTML grid.

    Deliberately NOT ``st.columns(7)``: Streamlit stacks columns below its
    mobile breakpoint, which turns a seven-across calendar into a 31-row
    list that buries everything under it — measured at 375px. A CSS grid
    stays a calendar at every width.

    Non-interactive by design. This is the Overview preview; selecting a day
    to inspect it belongs to the full Journal calendar, which has the room
    to show the result. Layout is inline (grid geometry only); every colour
    comes from a design-system class or token.
    """
    cells = [
        f'<div style="font-size:11px;letter-spacing:0.04em;text-transform:uppercase;'
        f'opacity:0.55;text-align:center">{name[:1]}</div>'
        for name in _WEEKDAYS
    ]
    for week in _cal.monthcalendar(year, month):
        for day in week:
            if day == 0:
                cells.append("<div></div>")
                continue
            info = daily.get(day_key(year, month, day))
            if info:
                dot_class = {
                    "positive": "tl-cal-dot positive",
                    "negative": "tl-cal-dot negative",
                }.get(info.get("outcome", ""), "tl-cal-dot")
                cells.append(
                    '<div style="text-align:center;padding:3px 0;'
                    'font-family:var(--tl-font-mono);font-size:12px">'
                    f'{day}<br/><span class="{dot_class}"></span></div>'
                )
            else:
                cells.append(
                    '<div style="text-align:center;padding:3px 0;opacity:0.35;'
                    'font-family:var(--tl-font-mono);font-size:12px">'
                    f"{day}</div>"
                )
    return (
        '<div style="display:grid;grid-template-columns:repeat(7,1fr);'
        'gap:2px;align-items:start">'
        f'{"".join(cells)}</div>'
    )


def render_trade_calendar(
    df,
    *,
    compact: bool = False,
    selected_date: str | None = None,
) -> None:
    """Render the monthly calendar for `df` trades.

    ``compact`` is the Overview preview: the grid and its month control only.
    The legend and the inline day table belong to the full view, where there
    is room to read them — in a side column they crowd out the calendar they
    are meant to explain. Full mode stays the default so the Analytics page
    is unaffected.

    ``selected_date`` pre-selects a day, letting a caller drive the panel
    without reaching into session state.
    """
    import streamlit as st

    from src.tradelens.services.metrics import daily_outcomes

    daily = daily_outcomes(df)
    if not daily:
        st.caption("No dated trades yet — the calendar fills in as you log.")
        return

    if selected_date and selected_date in daily:
        st.session_state[_SELECTED_KEY] = selected_date

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

    if compact:
        st.markdown(compact_month_html(year, month, daily), unsafe_allow_html=True)
        selected = st.session_state.get(_SELECTED_KEY)
        if selected and selected in daily:
            info = daily[selected]
            st.caption(
                f"{selected} · {info['trades']} trade(s) · net ${info['pnl']:,.2f}"
            )
        return

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
                # Outcome suffix feeds the CSS dot color (design_system.py).
                if cols[i].button(
                    str(day),
                    key=f"calday_{key}_{info['outcome']}",
                    width="stretch",
                    help=f"{info['trades']} trade(s) · net ${info['pnl']:,.2f}",
                ):
                    st.session_state[_SELECTED_KEY] = key
            else:
                cols[i].markdown(
                    f"<div style='text-align:center;opacity:0.45'>{day}</div>",
                    unsafe_allow_html=True,
                )

    if not compact:
        st.markdown(
            '<div class="tl-cal-legend">'
            '<span class="tl-cal-key">'
            '<span class="tl-cal-dot positive"></span>net positive day</span>'
            '<span class="tl-cal-key">'
            '<span class="tl-cal-dot negative"></span>net negative</span>'
            '<span class="tl-cal-key">'
            '<span class="tl-cal-dot"></span>breakeven</span>'
            "<span>click a day to review it</span></div>",
            unsafe_allow_html=True,
        )

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
            width="stretch",
        )
        if st.button("Close day view", key="dash_cal_close"):
            st.session_state.pop(_SELECTED_KEY, None)
            st.rerun()
