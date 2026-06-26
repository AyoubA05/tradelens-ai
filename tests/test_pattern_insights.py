"""
Deterministic pattern insights (Session C, Section 5).

These run without an AI key and must never raise on small / missing-column data.
"""

import pandas as pd

from src.tradelens.services.patterns import generate_insights


def _df(rows):
    return pd.DataFrame(rows)


def test_insights_empty_df_returns_empty():
    assert generate_insights(pd.DataFrame()) == []
    assert generate_insights(None) == []


def test_insights_with_small_sample_does_not_error():
    df = _df(
        [
            {"result": "Win", "pnl": 100.0, "killzone": "ny_am", "setup_type": "FVG"},
            {"result": "Loss", "pnl": -50.0, "killzone": "ny_am", "setup_type": "FVG"},
        ]
    )
    out = generate_insights(df)
    assert isinstance(out, list)
    # 2 trades → at least the "keep logging" nudge, all low confidence.
    assert any("Log" in i["body"] for i in out)
    assert all(i["confidence"] == "low" for i in out)


def test_insights_killzone_edge():
    rows = []
    # ny_am: 4 wins; london: 4 losses → clear best/worst split.
    for _ in range(4):
        rows.append({"result": "Win", "pnl": 200.0, "killzone": "ny_am"})
    for _ in range(4):
        rows.append({"result": "Loss", "pnl": -100.0, "killzone": "london"})
    out = generate_insights(_df(rows))
    titles = {i["title"] for i in out}
    assert "Strongest killzone" in titles
    assert "Weakest killzone" in titles
    best = next(i for i in out if i["title"] == "Strongest killzone")
    assert "New York AM" in best["body"]  # humanized label
    assert best["type"] == "positive"


def test_insights_mistake_impact():
    rows = [
        {"result": "Loss", "pnl": -300.0, "mistake_tags": '["FOMO Entry"]'},
        {"result": "Loss", "pnl": -200.0, "mistake_tags": '["FOMO Entry"]'},
        {"result": "Win", "pnl": 150.0, "mistake_tags": "[]"},
    ]
    out = generate_insights(_df(rows))
    mistake = next((i for i in out if i["title"] == "Most costly mistake"), None)
    assert mistake is not None
    assert "FOMO Entry" in mistake["body"]
    assert mistake["type"] == "negative"


def test_insights_confidence_scales_with_sample():
    # 30+ trades in one killzone → high confidence on that insight.
    rows = [{"result": "Win", "pnl": 100.0, "killzone": "ny_am"} for _ in range(35)]
    out = generate_insights(_df(rows))
    best = next(i for i in out if i["title"] == "Strongest killzone")
    assert best["confidence"] == "high"
