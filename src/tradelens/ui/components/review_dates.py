from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pandas as pd


def review_day_options(frame: pd.DataFrame) -> tuple[dt.date, ...]:
    trade_dates = frame.get("trade_date")
    if trade_dates is None:
        return ()
    parsed = pd.to_datetime(trade_dates, errors="coerce").dropna()
    return tuple(sorted(set(parsed.dt.date), reverse=True))


def review_week_options(frame: pd.DataFrame) -> tuple[dt.date, ...]:
    mondays = {
        day - dt.timedelta(days=day.weekday()) for day in review_day_options(frame)
    }
    return tuple(sorted(mondays, reverse=True))


def demo_rows_for_day(frame: pd.DataFrame, day: dt.date) -> list[SimpleNamespace]:
    if frame.get("trade_date") is None:
        return []
    day_iso = day.isoformat()
    selected = frame.loc[frame["trade_date"].astype(str) == day_iso]
    return [SimpleNamespace(**record) for record in selected.to_dict("records")]
