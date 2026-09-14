from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pandas as pd

from src.tradelens.services.review_periods import (  # noqa: F401
    review_day_options,
    review_week_options,
)


def demo_rows_for_day(frame: pd.DataFrame, day: dt.date) -> list[SimpleNamespace]:
    if frame.get("trade_date") is None:
        return []
    day_iso = day.isoformat()
    selected = frame.loc[frame["trade_date"].astype(str) == day_iso]
    return [SimpleNamespace(**record) for record in selected.to_dict("records")]
