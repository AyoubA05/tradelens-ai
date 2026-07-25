"""The account controls a user actually has to reach.

The services are unit-tested elsewhere; what these prove is that the
capability is wired to a control a person can find and use — a deletion
function nobody can invoke does not make a privacy policy true.

Each scenario boots in a subprocess with its own database, for the reason
documented in tests/app_boot_check.py.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tests" / "account_ui_check.py"
PAGES = ROOT / "src" / "tradelens" / "ui"


def _run(scenario: str, tmp_path, invite: str = "") -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite:///{tmp_path / 'ui.db'}"
    env["DEMO_MODE"] = "true"
    # Pinned, not inherited: Streamlit exports secrets.toml into os.environ on
    # first access, so whether signup is enabled would otherwise depend on
    # which tests ran first — and that changes the auth screen's widget tree.
    env["TRADELENS_INVITE_CODE"] = invite
    return subprocess.run(
        [sys.executable, str(RUNNER), str(ROOT), scenario],
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )


@pytest.mark.parametrize(
    "scenario",
    ["reset-panel", "settings-email", "settings-delete"],
)
def test_account_control_is_reachable(scenario, tmp_path):
    proc = _run(scenario, tmp_path)
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"


def test_reset_is_reachable_when_signup_is_enabled_too(tmp_path):
    """The sign-in screen has two shapes; recovery must exist in both."""
    proc = _run("reset-panel", tmp_path, invite="SECRET")
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"


# --- source contracts ------------------------------------------------------


def test_deletion_requires_a_typed_confirmation_phrase():
    """A destructive, irreversible action must not be one stray click."""
    src = (PAGES / "pages" / "9_Settings.py").read_text(encoding="utf-8")
    assert "DELETE MY ACCOUNT" in src
    assert 'key="secondary_delete_account"' in src


def test_deletion_signs_the_user_out():
    """Leaving a session pointing at a deleted user row is a broken state."""
    src = (PAGES / "pages" / "9_Settings.py").read_text(encoding="utf-8")
    block = src[src.index("Permanently delete my account") :]
    assert "sign_out()" in block


def test_settings_tells_the_user_what_deletion_removes():
    src = (PAGES / "pages" / "9_Settings.py").read_text(encoding="utf-8")
    # Compare on content, not layout: the warning is a wrapped implicit
    # concatenation, so phrases straddle source lines.
    flat = " ".join(src.split()).replace('" "', "")
    for promise in ("Strategy Profile", "chart image", "cannot be undone"):
        assert promise in flat, f"deletion warning omits {promise!r}"


def test_settings_discloses_what_deletion_keeps():
    """The policy says cost records survive; the UI must say so too."""
    src = (PAGES / "pages" / "9_Settings.py").read_text(encoding="utf-8")
    assert "accounting" in src


def test_reset_panel_never_renders_the_token():
    src = (PAGES / "components" / "auth_screen.py").read_text(encoding="utf-8")
    panel = src[
        src.index("def _render_reset_panel") : src.index("def render_auth_screen")
    ]
    # The panel may take a code as input; it must never print one.
    assert "issue_reset_token" not in panel
    assert "_reset_body" not in panel
