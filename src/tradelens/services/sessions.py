"""Killzone assignment engine for SMC/ICT trading sessions.

All killzones are defined in US Eastern Time (America/New_York), which handles
DST automatically via zoneinfo — no manual offset arithmetic needed.

Killzone windows (ET):
    asia         20:00 – 00:00  (evening prior to London open)
    london_open  02:00 – 05:00
    ny_am        07:00 – 10:00  (NYSE open / ICT kill-zone)
    ny_lunch     12:00 – 13:00
    ny_pm        13:30 – 16:00  (NYSE close / power hour)
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Optional
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# (name, start_ET, end_ET_inclusive)  — None end means "through 23:59:59"
_KILLZONES = [
    ("asia", time(20, 0), None),
    ("london_open", time(2, 0), time(4, 59, 59)),
    ("ny_am", time(7, 0), time(9, 59, 59)),
    ("ny_lunch", time(12, 0), time(12, 59, 59)),
    ("ny_pm", time(13, 30), time(15, 59, 59)),
]

KILLZONE_LABELS: dict = {
    "asia": "Asian Session",
    "london_open": "London Open",
    "ny_am": "New York AM",
    "ny_lunch": "New York Lunch",
    "ny_pm": "New York PM",
    "off_session": "Off Session",
}


def assign_killzone(entry_time_utc: datetime, tz: str = "UTC") -> Optional[str]:
    """Return the ICT killzone name for *entry_time_utc*, or None if off-session.

    Args:
        entry_time_utc: Entry datetime. If naive, assumed to be in *tz*.
                        If aware, *tz* is ignored.
        tz: IANA timezone string for a naive *entry_time_utc* (default "UTC").

    Returns:
        One of "asia", "london_open", "ny_am", "ny_lunch", "ny_pm", or None.
    """
    if entry_time_utc.tzinfo is None:
        entry_dt = entry_time_utc.replace(tzinfo=ZoneInfo(tz))
    else:
        entry_dt = entry_time_utc

    et_dt = entry_dt.astimezone(ET)
    t = et_dt.time()

    for name, start, end in _KILLZONES:
        if end is None:
            if t >= start:
                return name
        else:
            if start <= t <= end:
                return name
    return None
