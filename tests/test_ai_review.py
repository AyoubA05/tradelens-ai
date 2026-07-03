"""
AI Review component (journal + process grade on the live Journal page).

Rendering runs in Streamlit bare mode (widgets return defaults, no runtime) —
these tests assert the gating logic and that render paths don't crash. The
journal/grading services themselves are covered by test_journal / test_grading.
"""

from types import SimpleNamespace

import src.tradelens.ui.components.ai_review as comp


def _trade(**kw):
    base = {"id": 1, "ai_grade": "B", "user_grade": None}
    base.update(kw)
    return SimpleNamespace(**base)


def _analysis(**kw):
    base = {"id": 10, "journal_entry_md": None, "grading_json": None}
    base.update(kw)
    return SimpleNamespace(**base)


def test_disabled_ai_short_circuits(monkeypatch):
    monkeypatch.setattr(comp, "ai_available", lambda: False)
    called = {"analysis": False}
    monkeypatch.setattr(
        comp,
        "get_analysis_for_trade",
        lambda tid: called.__setitem__("analysis", True),
    )
    comp.render_ai_review(_trade())
    assert called["analysis"] is False  # gated before any DB access


def test_no_analysis_renders_guidance_without_crash(monkeypatch):
    monkeypatch.setattr(comp, "ai_available", lambda: True)
    monkeypatch.setattr(comp, "get_analysis_for_trade", lambda tid: None)
    comp.render_ai_review(_trade())  # must not raise


def test_with_saved_journal_and_grade_renders(monkeypatch):
    monkeypatch.setattr(comp, "ai_available", lambda: True)
    analysis = _analysis(
        journal_entry_md="### Setup Review\nGood entry.",
        grading_json=(
            '{"grade": "B", "score": 7, "one_line_verdict": "Solid process.", '
            '"rubric": {"rule_adherence": {"score": 8, "note": "Followed plan."}}}'
        ),
    )
    monkeypatch.setattr(comp, "get_analysis_for_trade", lambda tid: analysis)
    comp.render_ai_review(_trade(), strategy_profile={"name": "S"})  # must not raise


def test_none_trade_is_noop(monkeypatch):
    monkeypatch.setattr(comp, "ai_available", lambda: True)
    comp.render_ai_review(None)  # must not raise
