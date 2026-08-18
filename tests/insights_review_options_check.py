"""Exercise the Insights review-period choices through Streamlit AppTest.

This stays a subprocess helper because the Insights page imports services at
module scope. Keeping that module graph isolated avoids the duplicate-module
failure mode documented by ``app_boot_check.py``.
"""

from __future__ import annotations

import datetime as dt
import sys

import pandas as pd


def _rendered(at) -> str:
    return "\n".join([m.value for m in at.markdown] + [c.value for c in at.caption])


def _review(content: str, *, week_start: str | None = None) -> dict:
    return {
        "week_start": week_start,
        "empty": False,
        "content_md": content,
        "thinking_summary": None,
        "stats": {"trades": 5, "win_rate": 0.6, "total_pnl": 100.0},
        "cost_usd": 0.0,
    }


def _day_label(day: dt.date) -> str:
    return f"{day:%b} {day.day}, {day:%Y}"


def _week_label(monday: dt.date) -> str:
    sunday = monday + dt.timedelta(days=6)
    if monday.year != sunday.year:
        return f"{monday:%b} {monday.day}, {monday:%Y}–{sunday:%b} {sunday.day}, {sunday:%Y}"
    if monday.month == sunday.month:
        return f"{monday:%b} {monday.day}–{sunday.day}, {monday:%Y}"
    return f"{monday:%b} {monday.day}–{sunday:%b} {sunday.day}, {sunday:%Y}"


def main() -> int:
    root = sys.argv[1]
    sys.path.insert(0, root)

    try:
        import streamlit as st

        st.secrets._secrets = {}
    except Exception:  # noqa: BLE001 — same isolation guard as boot tests
        pass

    from src.tradelens.db.init_db import init_db

    init_db()

    from src.tradelens.services import cost as cost_service
    from src.tradelens.services import debrief as debrief_service
    from src.tradelens.services import demo, strategy, weekly as weekly_service
    from src.tradelens.services.ai_client import Usage
    from src.tradelens.ui.components.review_dates import (
        review_day_options,
        review_week_options,
    )

    from streamlit.testing.v1 import AppTest

    # Every user-facing service now requires a concrete owner (Ruling 10), so
    # an ownerless session is refused at the shared auth gate before the page
    # body runs at all. This harness boots signed in as a real owner, exactly
    # as production sessions always are.
    boot_uid = 1

    def _boot(lens: str, state: dict | None = None):
        at = AppTest.from_file(f"{root}/src/tradelens/ui/pages/6_Insights.py")
        at.session_state["authenticated"] = True
        at.session_state["current_user_id"] = boot_uid
        at.session_state["ai_review_lens"] = lens
        for key, value in (state or {}).items():
            at.session_state[key] = value
        at = at.run(timeout=120)
        if at.exception:
            raise RuntimeError(f"{lens} boot raised: {at.exception}")
        return at

    unpatched_weekly = _boot("Weekly Recap")
    unpatched_rendered = _rendered(unpatched_weekly)
    if "This week has nothing logged to review" in unpatched_rendered:
        print(
            "unpatched demo weekly review rendered the empty caption", file=sys.stderr
        )
        return 1
    if "What Worked" not in unpatched_rendered:
        print(
            "unpatched demo weekly review did not render its fixture", file=sys.stderr
        )
        return 2
    demo_monday = review_week_options(demo.get_demo_df())[0].isoformat()
    if weekly_service.get_weekly_review(demo_monday, boot_uid) is not None:
        print("unpatched demo weekly review wrote a saved note", file=sys.stderr)
        return 3

    frame = demo.get_demo_df(as_of=dt.date(2026, 8, 8))
    days = review_day_options(frame)
    weeks = review_week_options(frame)
    selected_day = days[1]
    selected_week = weeks[1]
    demo.get_demo_df = lambda: frame

    captured_strategy: list[dict | None] = []
    captured_day_trades: list[list] = []
    calls = {"daily": 0, "weekly": 0}
    writes = {"weekly": 0, "usage": 0}

    def _daily(day_trades, *, strategy_profile=None, **_kwargs):
        calls["daily"] += 1
        captured_strategy.append(strategy_profile)
        captured_day_trades.append(day_trades)
        return _review("## Daily demo review"), Usage("demo", 0, 0, 0, 0.0, 0.0)

    def _weekly(week_start, *_args, strategy_profile=None, **_kwargs):
        calls["weekly"] += 1
        captured_strategy.append(strategy_profile)
        return _review("## Weekly demo review", week_start=str(week_start)), Usage(
            "demo", 0, 0, 0, 0.0, 0.0
        )

    debrief_service.generate_debrief = _daily
    weekly_service.generate_weekly_review = _weekly
    strategy.get_active_strategy = lambda _uid: None

    def _save_weekly(*_args, **_kwargs):
        writes["weekly"] += 1

    def _log_usage(*_args, **_kwargs):
        writes["usage"] += 1

    weekly_service.save_weekly_review = _save_weekly
    cost_service.log_ai_usage = _log_usage

    daily = _boot("Daily Debrief", {"ins_dbf_day": selected_day})
    if "No trades logged on this day" in _rendered(daily):
        print(
            "daily review used database rows instead of the demo frame", file=sys.stderr
        )
        return 4
    daily_picker = daily.selectbox[0]
    if list(daily_picker.options) != [_day_label(day) for day in days]:
        print(
            f"daily options differed from populated demo days: {daily_picker.options}",
            file=sys.stderr,
        )
        return 5
    if daily_picker.value != selected_day:
        print(
            f"daily picker ignored selected day: {daily_picker.value}", file=sys.stderr
        )
        return 6
    generate = [
        b for b in daily.button if (b.label or "").startswith("Generate debrief")
    ]
    if not generate:
        print("daily demo review did not offer its populated day", file=sys.stderr)
        return 7
    daily = generate[0].click().run(timeout=120)
    if daily.exception:
        print(f"daily generation raised: {daily.exception}", file=sys.stderr)
        return 8
    expected_rows = frame.loc[frame["trade_date"] == selected_day.isoformat()]
    received_rows = captured_day_trades[-1] if captured_day_trades else []
    if [row.id for row in received_rows] != expected_rows["id"].tolist():
        print("daily generator did not receive the selected demo IDs", file=sys.stderr)
        return 9
    required_fields = (
        "trade_date",
        "asset",
        "direction",
        "session",
        "pnl",
        "rr_realized",
        "result",
        "followed_rules",
    )
    if not all(
        row.trade_date == selected_day.isoformat()
        and all(hasattr(row, field) for field in required_fields)
        for row in received_rows
    ):
        print(
            "daily generator rows lacked selected-day debrief fields", file=sys.stderr
        )
        return 10

    weekly = _boot("Weekly Recap", {"ins_wk_pick": selected_week})
    if "This week has nothing logged to review" in _rendered(weekly):
        print("weekly review offered a period with no demo trades", file=sys.stderr)
        return 11
    if "What Worked" not in _rendered(weekly):
        print("weekly review did not render the generated demo note", file=sys.stderr)
        return 12
    weekly_picker = weekly.selectbox[0]
    if list(weekly_picker.options) != [_week_label(monday) for monday in weeks]:
        print(
            f"weekly options differed from populated demo weeks: {weekly_picker.options}",
            file=sys.stderr,
        )
        return 13
    if weekly_picker.value != selected_week:
        print(
            f"weekly picker ignored selected week: {weekly_picker.value}",
            file=sys.stderr,
        )
        return 14

    if calls != {"daily": 1, "weekly": 0}:
        print(f"unexpected review calls: {calls}", file=sys.stderr)
        return 15
    if not all(
        profile and profile.get("name") == "ICT/SMC Day Trading"
        for profile in captured_strategy
    ):
        print(
            f"demo strategy was not passed to reviews: {captured_strategy}",
            file=sys.stderr,
        )
        return 16
    if writes != {"weekly": 0, "usage": 1}:
        print(f"unexpected populated-review writes: {writes}", file=sys.stderr)
        return 17

    before_empty = dict(writes)
    demo.get_demo_df = lambda: pd.DataFrame()
    empty_copy = {
        "Daily Debrief": (
            "No completed trading day to review",
            "Log completed trades, then return here for a daily debrief.",
        ),
        "Weekly Recap": (
            "No completed week to review",
            "Log completed trades, then return here for a weekly recap.",
        ),
    }
    for lens, expected_copy in empty_copy.items():
        empty = _boot(lens)
        rendered = _rendered(empty)
        if any(copy not in rendered for copy in (*expected_copy, "Open Journal →")):
            print(
                f"empty {lens} recovery copy was incomplete: {rendered}",
                file=sys.stderr,
            )
            return 18
        if calls != {"daily": 1, "weekly": 0}:
            print(
                f"empty {lens} review period called a generator: {calls}",
                file=sys.stderr,
            )
            return 19
        if writes != before_empty:
            print(f"empty {lens} recovery wrote data: {writes}", file=sys.stderr)
            return 20

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
