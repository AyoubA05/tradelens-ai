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


def month_summary(year: int, month: int, daily: dict) -> dict | None:
    """The month's standing, read off the same `daily_outcomes` map the grid
    draws from.

    Pure, and deliberately not in page code: the calendar owns which month is
    open, so the figures that describe that month belong beside it rather than
    recomputed by whichever page mounted it. Returns None for a month with no
    trading days — there is nothing to state, and a row of zeros would invent
    a flat month out of an untraded one.

    `winning_days` is counted in days, not trades, and is named that way. The
    map has no per-trade outcome, so a trade win rate is not derivable here,
    and labelling a day count "win rate" would be a different measure wearing
    the same word.
    """
    prefix = f"{year:04d}-{month:02d}-"
    days = {d: info for d, info in daily.items() if d.startswith(prefix)}
    if not days:
        return None
    best = max(days.items(), key=lambda kv: kv[1]["pnl"])
    worst = min(days.items(), key=lambda kv: kv[1]["pnl"])
    return {
        "net_pnl": sum(i["pnl"] for i in days.values()),
        "trades": sum(i["trades"] for i in days.values()),
        "trading_days": len(days),
        "winning_days": sum(1 for i in days.values() if i["outcome"] == "positive"),
        "best_day": best[0],
        "best_pnl": best[1]["pnl"],
        "worst_day": worst[0],
        "worst_pnl": worst[1]["pnl"],
    }


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

    Quiet days carry `--tl-content-secondary`, not an opacity. A day the
    trader did not trade is still a real date, and `opacity: 0.35` measured
    3.0:1 on 12px text against the canvas — a WCAG AA failure at every width,
    reproduced on all four. The design system already warns against exactly
    this substitution where it separates disabled from read-only inputs:
    dimming by opacity makes a real value look like a forbidden one. The
    content-secondary role says "quiet" and stays at 6.13-7.32:1.
    """
    cells = [
        f'<div style="font-size:11px;letter-spacing:0.04em;text-transform:uppercase;'
        f'color:var(--tl-content-secondary);text-align:center">{name[:1]}</div>'
        for name in _WEEKDAYS
    ]
    for week in _cal.monthcalendar(year, month):
        for day in week:
            if day == 0:
                cells.append("<div></div>")
                continue
            info = daily.get(day_key(year, month, day))
            if info:
                outcome = info.get("outcome", "")
                dot_class = {
                    "positive": "tl-cal-dot positive",
                    "negative": "tl-cal-dot negative",
                }.get(outcome, "tl-cal-dot")
                # The dot's meaning is carried by hue alone, so it is also
                # spelled out for anyone not reading the hue. Visually hidden,
                # not `title`: a tooltip needs a pointer and never reaches a
                # screen-reader user browsing the grid.
                outcome_text = {
                    "positive": "net positive",
                    "negative": "net negative",
                }.get(outcome, "breakeven")
                cells.append(
                    '<div style="text-align:center;padding:3px 0;'
                    'font-family:var(--tl-font-mono);font-size:12px">'
                    f'{day}<br/><span class="{dot_class}"></span>'
                    f'<span class="tl-visually-hidden">{outcome_text}</span>'
                    "</div>"
                )
            else:
                cells.append(
                    '<div style="text-align:center;padding:3px 0;'
                    "color:var(--tl-content-secondary);"
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
    show_month_summary: bool = False,
) -> "str | None":
    """Render the monthly calendar for `df` trades.

    Returns the selected day as an ISO "YYYY-MM-DD" string, or None when no
    day is open. Callers that want to act on the selection — the Journal
    offers openers for that day's trades — read the return value instead of
    reaching into session state. Overview and Analytics ignore it, so their
    behaviour is unchanged.

    ``compact`` is the Overview preview: the grid and its month control only.
    The legend and the inline day table belong to the full view, where there
    is room to read them — in a side column they crowd out the calendar they
    are meant to explain. Full mode stays the default so the Analytics page
    is unaffected.

    ``selected_date`` pre-selects a day, letting a caller drive the panel
    without reaching into session state.

    ``show_month_summary`` states the open month's standing above the grid,
    through the shared ruled strip. Off by default: the Journal reaches the
    calendar from a ledger that already carries the range's figures, so a
    second strip there would restate them for a different window under the
    same headings. Analytics turns it on, because the month the calendar has
    open is not the range its filters describe, and leaving that unstated is
    what made the old page's month figures read as range figures.
    """
    import streamlit as st

    from src.tradelens.services.metrics import daily_outcomes

    daily = daily_outcomes(df)
    if not daily:
        st.caption("No dated trades yet — the calendar fills in as you log.")
        return None

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
            return selected
        return None

    if show_month_summary:
        from src.tradelens.ui.components.overview_bands import money
        from src.tradelens.ui.components.workspace import MetricItem, render_kpi_strip

        summary = month_summary(year, month, daily)
        if summary:
            st.markdown(
                render_kpi_strip(
                    [
                        MetricItem(
                            f"{month_label(picked)} net",
                            money(summary["net_pnl"]),
                            detail=f"{summary['trades']} trades",
                            tone=(
                                "positive"
                                if summary["net_pnl"] > 0
                                else "negative" if summary["net_pnl"] < 0 else "neutral"
                            ),
                        ),
                        MetricItem(
                            "Winning days",
                            f"{summary['winning_days']}/{summary['trading_days']}",
                            detail="days traded this month",
                        ),
                        MetricItem(
                            "Best day",
                            money(summary["best_pnl"]),
                            detail=summary["best_day"],
                            tone="positive" if summary["best_pnl"] > 0 else "neutral",
                        ),
                        MetricItem(
                            "Worst day",
                            money(summary["worst_pnl"]),
                            detail=summary["worst_day"],
                            tone="negative" if summary["worst_pnl"] < 0 else "neutral",
                        ),
                    ]
                ),
                unsafe_allow_html=True,
            )

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
                    "<div style='text-align:center;"
                    f"color:var(--tl-content-secondary)'>{day}</div>",
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
        return selected
    return None
