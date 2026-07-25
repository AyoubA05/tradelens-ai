"""The operator's view of the beta, and its privacy boundary.

Knowing that 40% of accounts reach a first review is a product decision.
Knowing *which* trader didn't is surveillance the beta has no need for, so
the report is aggregate by construction: identity columns never enter the
computation and the output carries counts and rates only.
"""

from datetime import date

import pandas as pd

from scripts.beta_health import compute_beta_health, format_markdown


def test_beta_health_counts_users_and_activation_without_identity_fields():
    users = pd.DataFrame(
        [
            {"user_id": 1, "created_at": "2026-07-01"},
            {"user_id": 2, "created_at": "2026-07-02"},
        ]
    )
    milestones = pd.DataFrame(
        [
            {
                "user_id": 1,
                "has_strategy": True,
                "complete_trades": 5,
                "has_review": True,
            },
            {
                "user_id": 2,
                "has_strategy": True,
                "complete_trades": 1,
                "has_review": False,
            },
        ]
    )
    report = compute_beta_health(users, milestones, as_of=date(2026, 7, 21))
    assert report == {
        "accounts": 2,
        "strategy_rate": 1.0,
        "first_trade_rate": 1.0,
        "five_trade_rate": 0.5,
        "first_review_rate": 0.5,
        "activation_rate": 0.5,
    }
    assert "username" not in report


def test_empty_beta_reports_zeroes_rather_than_dividing_by_zero():
    report = compute_beta_health(
        pd.DataFrame(columns=["user_id", "created_at"]),
        pd.DataFrame(
            columns=["user_id", "has_strategy", "complete_trades", "has_review"]
        ),
        as_of=date(2026, 7, 21),
    )
    assert report["accounts"] == 0
    assert all(v == 0.0 for k, v in report.items() if k != "accounts")


def test_activation_requires_both_five_trades_and_a_review():
    """Either half alone is not activation."""
    users = pd.DataFrame([{"user_id": i, "created_at": "2026-07-01"} for i in (1, 2)])
    milestones = pd.DataFrame(
        [
            # five trades, never reviewed
            {
                "user_id": 1,
                "has_strategy": True,
                "complete_trades": 9,
                "has_review": False,
            },
            # reviewed, but on a thin sample
            {
                "user_id": 2,
                "has_strategy": True,
                "complete_trades": 2,
                "has_review": True,
            },
        ]
    )
    report = compute_beta_health(users, milestones, as_of=date(2026, 7, 21))
    assert report["activation_rate"] == 0.0
    assert report["five_trade_rate"] == 0.5
    assert report["first_review_rate"] == 0.5


def test_milestones_for_unknown_users_are_ignored():
    """A stale milestone row must not inflate a rate above 1.0."""
    users = pd.DataFrame([{"user_id": 1, "created_at": "2026-07-01"}])
    milestones = pd.DataFrame(
        [
            {
                "user_id": 1,
                "has_strategy": True,
                "complete_trades": 5,
                "has_review": True,
            },
            {
                "user_id": 99,
                "has_strategy": True,
                "complete_trades": 5,
                "has_review": True,
            },
        ]
    )
    report = compute_beta_health(users, milestones, as_of=date(2026, 7, 21))
    assert report["accounts"] == 1
    assert report["activation_rate"] == 1.0


def test_missing_milestone_rows_count_as_not_started():
    users = pd.DataFrame([{"user_id": i, "created_at": "2026-07-01"} for i in (1, 2)])
    milestones = pd.DataFrame(
        [{"user_id": 1, "has_strategy": True, "complete_trades": 5, "has_review": True}]
    )
    report = compute_beta_health(users, milestones, as_of=date(2026, 7, 21))
    assert report["accounts"] == 2
    assert report["activation_rate"] == 0.5


def test_markdown_output_contains_no_identity_or_trade_data():
    report = {
        "accounts": 3,
        "strategy_rate": 0.667,
        "first_trade_rate": 0.667,
        "five_trade_rate": 0.333,
        "first_review_rate": 0.333,
        "activation_rate": 0.333,
    }
    text = format_markdown(report, as_of=date(2026, 7, 21)).lower()
    for term in ("username", "email", "pnl", "trade_date", "notes", "screenshot"):
        assert term not in text
    assert "3" in text


def test_report_keys_are_stable():
    """The scorecard doc and this output must not drift apart."""
    report = compute_beta_health(
        pd.DataFrame(columns=["user_id", "created_at"]),
        pd.DataFrame(
            columns=["user_id", "has_strategy", "complete_trades", "has_review"]
        ),
        as_of=date(2026, 7, 21),
    )
    assert set(report) == {
        "accounts",
        "strategy_rate",
        "first_trade_rate",
        "five_trade_rate",
        "first_review_rate",
        "activation_rate",
    }
