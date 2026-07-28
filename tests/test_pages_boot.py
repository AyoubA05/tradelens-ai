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

# Session A: the sidebar now exposes exactly these five pages (plus app.py, the
# Dashboard, covered by test_dashboard). Home/TradeDetail/Calendar/Weekly/AI
# Partner moved to pages/_archive/ (Calendar + Weekly are now Analytics tabs).
ALL_PAGES = [
    "1_NewTrade.py",
    "2_Trades.py",
    "4_Analytics.py",
    "5_Strategy.py",
    "6_Insights.py",
    "9_Settings.py",
]

# Read-only data pages worth booting with rows present.
SEED_PAGES = ["2_Trades.py", "4_Analytics.py", "6_Insights.py"]


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


# ---------------------------------------------------------------------------
# Shell contract — the custom navigation is the ONLY navigation
# ---------------------------------------------------------------------------


def test_streamlits_own_page_navigation_stays_disabled():
    """TradeLens renders its own labelled rail. With Streamlit's automatic
    nav also on, a trader sees two menus listing the same pages under
    different names — the file names, which say `6_Insights`."""
    config = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert "showSidebarNavigation = false" in config


@pytest.mark.parametrize("page", ALL_PAGES)
def test_every_page_renders_the_custom_shell(page):
    """A page that forgets the shell loses navigation entirely — there is no
    fallback menu to fall back to."""
    src = (PAGES_DIR / page).read_text(encoding="utf-8")
    assert "render_sidebar" in src, f"{page} renders no navigation"


def test_the_entrypoint_renders_the_custom_shell():
    src = (ROOT / "src" / "tradelens" / "ui" / "app.py").read_text(encoding="utf-8")
    assert "render_sidebar" in src


def test_no_page_hardcodes_its_own_navigation_list():
    """Navigation lives in components/sidebar.py. A page building its own
    list is how the rail and the page disagree about what exists."""
    pages = [PAGES_DIR / p for p in ALL_PAGES]
    pages.append(ROOT / "src" / "tradelens" / "ui" / "app.py")
    for path in pages:
        src = path.read_text(encoding="utf-8")
        assert "PRIMARY_NAV = " not in src, f"{path.name} redefines the nav"
        assert "MOBILE_NAV = " not in src, f"{path.name} redefines the mobile nav"
