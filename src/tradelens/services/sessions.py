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

from datetime import datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_ET_NAME = "America/New_York"
# Fixed Eastern Standard offset, used ONLY as a last resort when the IANA tz
# database is missing (e.g. a minimal container without the `tzdata` package),
# so importing this module never raises ZoneInfoNotFoundError on Streamlit Cloud.
_ET_FALLBACK = timezone(timedelta(hours=-5))


def _zone(name: str):
    """tzinfo for `name`, falling back to a fixed offset instead of raising when
    the tz database is unavailable — keeps module import safe."""
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, KeyError, ValueError, OSError):
        return _ET_FALLBACK


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


def parse_time_input(value):
    """Parse a typed entry time into a datetime.time, or None if unparseable.

    Accepts '09:30', '9:30 AM', '2:05 PM', '14:05', '0930', a time, or a datetime.
    """
    if value is None:
        return None
    if isinstance(value, time):
        return value
    if isinstance(value, datetime):
        return value.time()
    text = str(value).strip().upper().replace(".", "")
    if not text:
        return None
    for fmt in ("%H:%M", "%I:%M %p", "%I:%M%p", "%H%M", "%I %p"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


def _coerce_local_time(value, user_timezone: str):
    """Return a datetime.time in the user's wall-clock, or None if unparseable.

    A naive time/datetime is taken as already-local; a tz-aware datetime is
    converted into `user_timezone`; an 'HH:MM' string is parsed as local.
    """
    if value is None:
        return None
    if isinstance(value, time):
        return value
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(_zone(user_timezone)).time()
        return value.time()
    if isinstance(value, str):
        try:
            parts = value.strip().split(":")
            return time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
        except (ValueError, IndexError):
            return None
    return None


def detect_killzone(
    entry_time, trade_date=None, user_timezone: str = "America/New_York"
) -> str:
    """Map a LOCAL entry time to a trading-session killzone key.

    `entry_time` may be a datetime.time, a datetime, or an 'HH:MM' string and is
    interpreted as the trader's wall-clock time in `user_timezone` (so it never
    depends on the server timezone). Session windows (local):

        Asian Session  18:00–01:59     London Session 02:00–09:29
        NY AM          09:30–11:59      NY Lunch       12:00–12:59
        NY PM          13:00–15:59      Off Session    16:00–17:59

    Returns one of: 'asia', 'london_open', 'ny_am', 'ny_lunch', 'ny_pm',
    'off_session'. `trade_date` is accepted for future DST/holiday refinement.
    """
    t = _coerce_local_time(entry_time, user_timezone)
    if t is None:
        return "off_session"
    minutes = t.hour * 60 + t.minute
    if minutes >= 18 * 60 or minutes < 2 * 60:
        return "asia"
    if minutes < 9 * 60 + 30:
        return "london_open"
    if minutes < 12 * 60:
        return "ny_am"
    if minutes < 13 * 60:
        return "ny_lunch"
    if minutes < 16 * 60:
        return "ny_pm"
    return "off_session"


# Market-session labels (New Trade "Market Context", Part 2 Change B). Derived
# automatically from the entry time — there is no manual session input. Windows
# are the spec's ET ranges; New York Open wins the 09:30–10:00 sliver it shares
# with the London/NY Overlap so each session keeps a single primary identity.
SESSION_LABELS = [
    "Pre-Market",
    "London/NY Overlap",
    "New York Open",
    "Midday",
    "Power Hour",
    "After Hours",
    "Off-Hours",
]


def detect_session(
    entry_time, trade_date=None, user_timezone: str = "America/New_York"
) -> str:
    """Auto-derive the market session from a local entry time (Part 2 Change B).

    The typed entry time is read as the trader's wall-clock (same convention as
    detect_killzone) and mapped to a session label:

        Pre-Market         06:00–08:00     London/NY Overlap 08:00–09:30*
        New York Open      09:30–11:30      Midday            11:30–14:00
        Power Hour         14:00–16:00      After Hours       16:00–18:00

    *The spec lists the Overlap as 08:00–10:00; New York Open is checked first so
    the shared 09:30–10:00 window resolves to New York Open. Anything outside all
    windows is "Off-Hours". `trade_date` is accepted for future DST refinement.
    """
    t = _coerce_local_time(entry_time, user_timezone)
    if t is None:
        return "Off-Hours"
    m = t.hour * 60 + t.minute
    if 9 * 60 + 30 <= m < 11 * 60 + 30:
        return "New York Open"
    if 11 * 60 + 30 <= m < 14 * 60:
        return "Midday"
    if 14 * 60 <= m < 16 * 60:
        return "Power Hour"
    if 6 * 60 <= m < 8 * 60:
        return "Pre-Market"
    if 16 * 60 <= m < 18 * 60:
        return "After Hours"
    if 8 * 60 <= m < 10 * 60:
        return "London/NY Overlap"
    return "Off-Hours"


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
        entry_dt = entry_time_utc.replace(tzinfo=_zone(tz))
    else:
        entry_dt = entry_time_utc

    et_dt = entry_dt.astimezone(_zone(_ET_NAME))
    t = et_dt.time()

    for name, start, end in _KILLZONES:
        if end is None:
            if t >= start:
                return name
        else:
            if start <= t <= end:
                return name
    return None
