"""
Lightweight persistent app settings (Session E1).

A JSON-backed key/value store in the ``data/`` directory — the same persistence
boundary as the SQLite DB — so a preference like the trading timezone survives
reruns and app restarts WITHOUT a schema change or migration. Streamlit-free and
testable (the path is module-level and monkeypatchable).
"""

from __future__ import annotations

import json
from pathlib import Path

_SETTINGS_PATH = Path(__file__).resolve().parents[3] / "data" / "app_settings.json"

DEFAULT_TIMEZONE = "America/New_York"


def _read() -> dict:
    try:
        return json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        return {}


def get_setting(key: str, default=None):
    """Return a stored setting, or `default` if unset/unreadable."""
    return _read().get(key, default)


def set_setting(key: str, value) -> None:
    """Persist a setting (creates the data/ dir + file as needed)."""
    data = _read()
    data[key] = value
    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_timezone() -> str:
    """The trader's saved timezone, falling back to America/New_York."""
    return get_setting("trading_timezone", DEFAULT_TIMEZONE) or DEFAULT_TIMEZONE


def set_timezone(tz: str) -> None:
    """Persist the trader's timezone (empty falls back to the default)."""
    set_setting("trading_timezone", tz or DEFAULT_TIMEZONE)
