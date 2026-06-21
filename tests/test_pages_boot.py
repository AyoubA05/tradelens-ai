"""
Boot smoke tests for all 9 pages (Phase 3, week6-d3).

Each page is booted under AppTest in a SUBPROCESS with an isolated tmp DB (see
app_boot_check.py for why a subprocess and not an in-process module reload). The
empty-DB boots exercise the designed empty-state paths; the seed-DB boots cover
the read-only data pages with rows present. Marker "-" means boot-only: assert
the page raises no exception.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGES_DIR = ROOT / "src" / "tradelens" / "ui" / "pages"
RUNNER = ROOT / "tests" / "app_boot_check.py"

ALL_PAGES = [
    "0_Home.py",
    "1_NewTrade.py",
    "2_Trades.py",
    "3_TradeDetail.py",
    "4_Analytics.py",
    "5_Strategy.py",
    "6_Calendar.py",
    "7_Weekly_Review.py",
    "8_AI_Partner.py",
    "9_Settings.py",
]

# Read-only data pages worth booting with rows present.
SEED_PAGES = ["2_Trades.py", "4_Analytics.py", "6_Calendar.py"]


def _boot(page: str, db_path: Path, seed: str):
    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["DEMO_MODE"] = "true"  # never touch the network on boot
    proc = subprocess.run(
        [sys.executable, str(RUNNER), str(ROOT), str(PAGES_DIR / page), "-", seed],
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, (
        f"{page} boot failed (rc={proc.returncode})\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )


@pytest.mark.parametrize("page", ALL_PAGES)
def test_page_boots_empty_db(page, tmp_path):
    _boot(page, tmp_path / "empty.db", "0")


@pytest.mark.parametrize("page", SEED_PAGES)
def test_page_boots_seed_db(page, tmp_path):
    _boot(page, tmp_path / "seed.db", "1")
