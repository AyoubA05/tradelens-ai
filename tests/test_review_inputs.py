"""`services/review_inputs` — the effective-input fingerprint (decision C2)."""

from __future__ import annotations

import pytest

from src.tradelens.services import ai_client, review_inputs, trade_analysis, weekly


def _input(**extra):
    base = {
        "week_start": "2026-09-07",
        "week_end": "2026-09-13",
        "stats": {"trades": 1, "win_rate": 1.0},
        "candidates": None,
        "strategy_profile": None,
        "source_trade_ids": [1],
    }
    base.update(extra)
    return base


def _fp(owner, model_input, kind="weekly_recap", period="2026-09-07"):
    return review_inputs.review_input_fingerprint(kind, owner, period, model_input)


def test_same_input_same_fingerprint(two_users):
    a, _ = two_users
    assert _fp(a, _input()) == _fp(a, _input())
    assert len(_fp(a, _input())) == 64


def test_owner_kind_period_and_payload_each_change_it(two_users):
    a, b = two_users
    base = _fp(a, _input())
    assert _fp(b, _input()) != base
    assert _fp(a, _input(), kind="daily_debrief") != base
    assert _fp(a, _input(), period="2026-08-31") != base
    assert _fp(a, _input(stats={"trades": 1, "win_rate": 0.5})) != base


def test_prompt_text_change_changes_it(two_users, monkeypatch):
    a, _ = two_users
    base = _fp(a, _input())
    real = ai_client.load_prompt
    monkeypatch.setattr(ai_client, "load_prompt", lambda name: real(name) + " edit")
    assert _fp(a, _input()) != base


def test_effort_change_changes_it(two_users, monkeypatch):
    a, _ = two_users
    base = _fp(a, _input())
    monkeypatch.setattr(weekly, "WEEKLY_EFFORT", "medium")
    assert _fp(a, _input()) != base


def test_ai_input_version_change_changes_it(two_users, monkeypatch):
    a, _ = two_users
    base = _fp(a, _input())
    monkeypatch.setattr(trade_analysis, "ai_input_version", lambda owner: "other")
    assert _fp(a, _input()) != base


def test_unavailable_ai_context_refuses(two_users, monkeypatch):
    a, _ = two_users

    def _raise(owner):
        raise trade_analysis.AIInputVersionUnavailable("x")

    monkeypatch.setattr(trade_analysis, "ai_input_version", _raise)
    with pytest.raises(trade_analysis.AIInputVersionUnavailable):
        _fp(a, _input())


def test_unknown_kind_is_refused(two_users):
    a, _ = two_users
    with pytest.raises(ValueError):
        _fp(a, _input(), kind="trade_summary")


def test_non_finite_numbers_fingerprint_deterministically(two_users):
    a, _ = two_users
    nan = _input(stats={"x": float("nan")})
    assert _fp(a, nan) == _fp(a, _input(stats={"x": float("nan")}))
    assert _fp(a, nan) != _fp(a, _input(stats={"x": float("inf")}))
