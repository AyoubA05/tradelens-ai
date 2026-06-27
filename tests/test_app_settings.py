"""
Persistent app settings (Session E1): timezone fallback + persistence.
"""

import importlib

import pytest

import src.tradelens.services.app_settings as app_settings


@pytest.fixture
def tmp_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "_SETTINGS_PATH", tmp_path / "app_settings.json")
    return app_settings


def test_timezone_defaults_when_unset(tmp_settings):
    assert tmp_settings.get_timezone() == "America/New_York"


def test_timezone_persists(tmp_settings):
    tmp_settings.set_timezone("Europe/London")
    assert tmp_settings.get_timezone() == "Europe/London"
    # A fresh read of the same file still returns it.
    assert tmp_settings.get_setting("trading_timezone") == "Europe/London"


def test_empty_timezone_falls_back(tmp_settings):
    tmp_settings.set_timezone("")
    assert tmp_settings.get_timezone() == "America/New_York"


def test_corrupt_settings_file_falls_back(tmp_settings, tmp_path):
    (tmp_path / "app_settings.json").write_text("not json{", encoding="utf-8")
    assert tmp_settings.get_timezone() == "America/New_York"


def test_other_settings_roundtrip(tmp_settings):
    tmp_settings.set_setting("foo", "bar")
    assert tmp_settings.get_setting("foo") == "bar"
    assert tmp_settings.get_setting("missing", "fallback") == "fallback"


def test_module_import_is_streamlit_free():
    # Re-import must not require Streamlit (services stay UI-free).
    mod = importlib.reload(app_settings)
    assert hasattr(mod, "get_timezone")
