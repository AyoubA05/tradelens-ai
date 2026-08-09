"""
Gates for the DEMO_MODE system (Phase 4, week6-d4): services/demo.py
(get_demo_df, is_demo, load_demo_fixture) and the end-to-end zero-network
guarantee for every AI feature.
"""

import datetime as dt
import io
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from PIL import Image

from src.tradelens.config import settings

# The confirmed Week 5 SMC/ICT column set (model names — asset, rr_realized).
DEMO_COLUMNS = [
    "trade_date",
    "asset",
    "direction",
    "entry_price",
    "exit_price",
    "pnl",
    "result",
    "rr_realized",
    "ai_grade",
    "user_grade",
    "killzone",
    "htf_bias",
    "liquidity_sweep",
    "fvg_used",
    "order_block_used",
    "bos",
    "choch",
    "confirmation_model",
    "entry_type",
    "mistake_tags",
    "followed_rules",
    "emotions_before",
    "emotions_during",
    "emotions_after",
]


# ---------------------------------------------------------------------------
# get_demo_df
# ---------------------------------------------------------------------------


def test_get_demo_df_has_all_columns():
    from src.tradelens.services.demo import get_demo_df

    df = get_demo_df()
    for col in DEMO_COLUMNS:
        assert col in df.columns, f"demo df missing required column: {col}"


def test_get_demo_df_row_count():
    from src.tradelens.services.demo import get_demo_df

    assert len(get_demo_df()) == 60


def test_get_demo_df_has_wins_and_losses():
    from src.tradelens.services.demo import get_demo_df

    results = set(get_demo_df()["result"].str.lower())
    assert "win" in results and "loss" in results


def test_get_demo_df_no_db_access():
    """Demo data is synthetic — it must never query the database."""
    from src.tradelens.services.demo import get_demo_df

    with patch("src.tradelens.db.session.SessionLocal") as mock_session:
        df = get_demo_df()
    mock_session.assert_not_called()
    assert not df.empty


def test_demo_rows_never_extend_beyond_the_supplied_view_date():
    from src.tradelens.services.demo import get_demo_df

    frame = get_demo_df(as_of=dt.date(2026, 8, 8))
    dates = frame["trade_date"].map(dt.date.fromisoformat)

    assert len(frame) == 60
    assert dates.max() <= dt.date(2026, 8, 8)
    assert all(day.weekday() < 5 for day in dates)


def test_demo_rows_are_deterministic_for_one_anchor():
    from src.tradelens.services.demo import get_demo_df

    left = get_demo_df(as_of=dt.date(2026, 8, 8))
    right = get_demo_df(as_of=dt.date(2026, 8, 8))

    assert left.to_dict("records") == right.to_dict("records")
    assert left.iloc[-1]["trade_date"] == "2026-08-07"


# ---------------------------------------------------------------------------
# is_demo
# ---------------------------------------------------------------------------


def test_is_demo_reads_settings(monkeypatch):
    from src.tradelens.services.demo import is_demo

    monkeypatch.setattr(settings, "demo_mode", True)
    assert is_demo() is True
    monkeypatch.setattr(settings, "demo_mode", False)
    assert is_demo() is False


# ---------------------------------------------------------------------------
# load_demo_fixture
# ---------------------------------------------------------------------------


def test_load_demo_fixture_returns_string():
    from src.tradelens.services.demo import load_demo_fixture

    out = load_demo_fixture("vision")
    assert isinstance(out, str) and out, "expected the vision 'default' fixture string"


def test_load_demo_fixture_missing_trade_id_falls_back():
    from src.tradelens.services.demo import load_demo_fixture

    # An unknown trade_id falls back to the feature's default (never None when
    # the feature file exists with a default).
    out = load_demo_fixture("vision", trade_id=999999)
    assert isinstance(out, str) and out


def test_load_demo_fixture_unknown_feature_returns_none():
    from src.tradelens.services.demo import load_demo_fixture

    assert load_demo_fixture("not_a_feature") is None


def test_load_demo_fixture_never_raises():
    from src.tradelens.services.demo import load_demo_fixture

    # Bad inputs must not raise — always return something renderable or None.
    assert load_demo_fixture("", trade_id=None) is None
    assert load_demo_fixture("vision", trade_id="bad") is not None


# ---------------------------------------------------------------------------
# Zero-network guarantee for EVERY AI feature in DEMO_MODE
# ---------------------------------------------------------------------------


def _tmp_jpeg(tmp_path: Path) -> Path:
    p = tmp_path / "chart.jpg"
    buf = io.BytesIO()
    Image.new("RGB", (2, 2), (120, 120, 120)).save(buf, format="JPEG")
    p.write_bytes(buf.getvalue())
    return p


def _invoke_vision(tmp_path):
    from src.tradelens.services.vision import analyze_screenshot

    analyze_screenshot(_tmp_jpeg(tmp_path), {"asset": "NQ", "id": 1})


def _invoke_grade(tmp_path):
    from src.tradelens.services.grading import grade_trade

    grade_trade(
        {"id": 1, "asset": "NQ", "direction": "Long", "result": "Win", "pnl": 100.0},
        None,
        {"bias": "bullish"},
    )


def _invoke_journal(tmp_path):
    from src.tradelens.services.journal import generate_journal

    generate_journal(
        {"id": 1, "asset": "NQ", "direction": "Long", "result": "Win"},
        {"bias": "bullish"},
        strategy_profile=None,
    )


def _invoke_weekly(tmp_path):
    from types import SimpleNamespace

    from src.tradelens.services import weekly

    fake = SimpleNamespace(
        trade_date="2026-06-15",
        day_of_week="Monday",
        result="Win",
        pnl=100.0,
        rr_realized=2.0,
        killzone="ny_am",
        confirmation_model="BOS",
        mistake_tags="[]",
        htf_bias="bullish",
        setup_type="FVG",
        followed_rules=1,
    )
    with patch.object(weekly, "get_trades", return_value=[fake]):
        weekly.generate_weekly_review("2026-06-15")


def _invoke_patterns(tmp_path):
    from src.tradelens.services.patterns import detect_patterns

    df = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-15",
                "asset": "NQ",
                "result": "Win",
                "pnl": 100.0,
                "killzone": "ny_am",
                "followed_rules": 1,
                "mistake_tags": "[]",
            }
            for _ in range(6)
        ]
    )
    detect_patterns(df)


def _invoke_partner(tmp_path):
    from src.tradelens.services.partner import partner_reply

    partner_reply(
        [{"role": "user", "content": "Review my trade process."}],
        trade_context="COMPLETED TRADE",
        strategy_profile=None,
        image_b64=None,
    )


_INVOKERS = {
    "vision": _invoke_vision,
    "grade": _invoke_grade,
    "journal": _invoke_journal,
    "weekly": _invoke_weekly,
    "patterns": _invoke_patterns,
    "partner": _invoke_partner,
}


@pytest.mark.parametrize("feature", list(_INVOKERS))
def test_demo_mode_zero_network(feature, tmp_path, monkeypatch):
    """In DEMO_MODE every feature returns renderable output and the Anthropic
    client is never constructed."""
    import src.tradelens.services.ai_client as ai_client

    monkeypatch.setattr(settings, "demo_mode", True)
    # keep correction injection hermetic (it runs even in demo mode)
    monkeypatch.setattr(
        ai_client, "build_correction_few_shot", lambda **k: "", raising=False
    )

    with patch.object(ai_client, "_get_client") as mock_client:
        _INVOKERS[feature](tmp_path)

    mock_client.assert_not_called()
