"""
Gates for the landing page 0_Home.py (Phase 4, week6-d4).

The hardest gate — and the one written first — is that the landing page imports
NOTHING from the database layer: it must render with zero data access so it is
instant and never errors on an empty/cold deploy. The rest enforce the hero
copy, honest no-signals scope (R5), the static-HTML comparison table, the
3-step strip, and the shared demo banner.
"""

from pathlib import Path

LANDING = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "tradelens"
    / "ui"
    / "pages"
    / "_archive"
    / "0_Home.py"
)

# Anything that would pull in the database / ORM / data services.
_DB_TOKENS = [
    "get_trades",
    "SessionLocal",
    "db.models",
    "db.session",
    "trade_service",
    "import Trade",
    "from src.tradelens.db",
]


def _src() -> str:
    return LANDING.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Hardest gate — zero DB imports (written first)
# ---------------------------------------------------------------------------


def test_landing_has_no_db_imports():
    src = _src()
    for token in _DB_TOKENS:
        assert token not in src, f"0_Home.py must not reference the DB layer: {token!r}"


# ---------------------------------------------------------------------------
# Content gates
# ---------------------------------------------------------------------------


def test_landing_hero_copy():
    assert "reviews every chart" in _src()


def test_landing_scope_note():
    assert "does not generate signals" in _src()


def test_landing_three_steps():
    src = _src()
    assert "Log" in src and "AI reviews" in src and "You improve" in src


def test_landing_comparison_is_static_html_not_widget():
    src = _src()
    assert "TradeZella" in src and "Edgewonk" in src and "TraderSync" in src
    assert "<table" in src, "comparison must be static HTML"
    assert "st.dataframe(" not in src and "st.table(" not in src


def test_landing_uses_shared_demo_banner():
    assert "render_demo_banner" in _src()


# ---------------------------------------------------------------------------
# R5 — no predictive / signal language (the disclaimer is allowed)
# ---------------------------------------------------------------------------

_PREDICTIVE = [
    "buy signal",
    "sell signal",
    "price will",
    "will go up",
    "will go down",
    "we predict",
    "our forecast",
    "trade recommendation",
    "next week's move",
    "tomorrow's move",
    "entry signal",
    "exit signal",
]


_NEGATIONS = ("not", "no ", "never", "doesn't", "does not", "without")


def test_landing_no_predictive_language():
    """R5: predictive phrasing is only allowed inside a negated disclaimer
    (e.g. 'does not generate trade recommendations')."""
    low = _src().lower()
    for phrase in _PREDICTIVE:
        idx = low.find(phrase)
        while idx != -1:
            window = low[max(0, idx - 45) : idx]
            assert any(
                neg in window for neg in _NEGATIONS
            ), f"0_Home.py has non-negated predictive language: {phrase!r}"
            idx = low.find(phrase, idx + 1)
