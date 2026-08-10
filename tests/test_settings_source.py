"""Contract for the shared settings accessor (defect D2).

The bug this closes was not a crash. Two modules read the same nominal setting
through different paths, so on Streamlit Cloud one found it and the other did
not, and each carried on believing it was correctly configured.
"""

from __future__ import annotations

import ast
from pathlib import Path

from src.tradelens import settings_source

_SRC = Path(__file__).parent.parent / "src" / "tradelens"


def test_environment_wins_over_the_default(monkeypatch):
    monkeypatch.setenv("TRADELENS_TEST_KEY", "from-env")
    assert settings_source.read_setting("TRADELENS_TEST_KEY", "fallback") == "from-env"


def test_missing_setting_falls_back_to_the_default(monkeypatch):
    monkeypatch.delenv("TRADELENS_TEST_KEY", raising=False)
    assert settings_source.read_setting("TRADELENS_TEST_KEY", "fallback") == "fallback"


def test_a_blank_environment_value_does_not_mask_the_default(monkeypatch):
    """An empty env var is what an unset CI variable looks like by the time it
    arrives here, and it must not read as "configured with nothing"."""
    monkeypatch.setenv("TRADELENS_TEST_KEY", "")
    assert settings_source.read_setting("TRADELENS_TEST_KEY", "fallback") == "fallback"


def test_reset_and_auth_derive_the_same_session_secret(monkeypatch):
    """D2 regression.

    password_reset used os.getenv only; auth also consulted st.secrets. On
    Streamlit Cloud that produced two different signing keys from one setting,
    so reset tokens were signed with a random per-process key while session
    tokens were signed with the configured one.
    """
    monkeypatch.setenv("TRADELENS_SESSION_SECRET", "shared-secret-value")

    from src.tradelens.services import password_reset
    from src.tradelens.ui.components import auth

    assert password_reset._base_secret() == auth._session_secret()
    assert password_reset._base_secret() == b"shared-secret-value"


def test_no_module_reads_a_deployment_setting_via_os_getenv_directly():
    """The split that caused D2 is now a test failure rather than a surprise.

    Any module reaching for one of these names through os.getenv bypasses the
    st.secrets fallback and will silently misbehave on Streamlit Cloud.
    """
    offenders = []
    for path in _SRC.rglob("*.py"):
        if path.name == "settings_source.py":
            continue
        try:
            tree = ast.parse(path.read_text(), filename=str(path))
        except SyntaxError:  # pragma: no cover - not our source to fix
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_getenv = (
                isinstance(func, ast.Attribute)
                and func.attr == "getenv"
                and isinstance(func.value, ast.Name)
                and func.value.id == "os"
            )
            if not is_getenv or not node.args:
                continue
            first = node.args[0]
            if (
                isinstance(first, ast.Constant)
                and first.value in settings_source.SETTING_NAMES
            ):
                offenders.append(f"{path.relative_to(_SRC)}: {first.value}")

    assert not offenders, (
        "these read a deployment setting directly and will miss st.secrets "
        f"on Streamlit Cloud: {offenders}"
    )
