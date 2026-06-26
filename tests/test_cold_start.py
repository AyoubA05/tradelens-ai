"""
Cold-start test (Phase 7, week6-d7).

Proves the app boots cleanly on a FRESH, EMPTY database — the exact first-load
condition on a cold Streamlit Community Cloud deploy — with DEMO_MODE=true so no
network call is made. Booting happens in a SUBPROCESS with an isolated tmp SQLite
DB (see app_boot_check.py for why a subprocess, not an in-process module reload).
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tests" / "app_boot_check.py"
ENTRY = ROOT / "src" / "tradelens" / "ui" / "app.py"
HOME = ROOT / "src" / "tradelens" / "ui" / "pages" / "_archive" / "0_Home.py"


def _cold_boot(
    app_path: Path, marker: str, tmp_path: Path
) -> subprocess.CompletedProcess:
    """Boot a page in a child process against a fresh empty DB, DEMO_MODE on."""
    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite:///{tmp_path / 'cold.db'}"  # fresh, empty
    env["DEMO_MODE"] = "true"  # zero API calls on first load
    return subprocess.run(
        [sys.executable, str(RUNNER), str(ROOT), str(app_path), marker, "0"],
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )


def test_cold_start_entry_app_boots(tmp_path):
    """The deploy entry point renders on an empty DB without raising."""
    proc = _cold_boot(ENTRY, "-", tmp_path)  # "-" = boot-only, assert no exception
    assert proc.returncode == 0, (
        f"cold start of app.py failed (rc={proc.returncode})\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )


def test_cold_start_home_renders(tmp_path):
    """The Home/landing page renders its hero on a cold, empty deploy."""
    proc = _cold_boot(HOME, "reviews every chart", tmp_path)
    assert proc.returncode == 0, (
        f"cold start of 0_Home.py failed (rc={proc.returncode})\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
