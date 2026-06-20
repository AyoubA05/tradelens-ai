"""
AI cost observability.

Aggregates persisted AI spend for a calendar month, grouped by feature, for the
Settings cost dashboard. The only tables that persist cost are ai_analysis (the
per-trade vision/journal/grading pipeline) and weekly_reviews. Pattern detection
and the AI Partner are per-session and not persisted — see Known Issues.

No Streamlit imports here.
"""

import pandas as pd

from src.tradelens.db.models import AIAnalysis, WeeklyReview
from src.tradelens.db.session import SessionLocal

_COST_COLS = ["feature", "cost_usd", "calls"]

_TRADE_ANALYSIS = "Trade Analysis (vision/journal/grading)"
_WEEKLY_REVIEW = "Weekly Review"


def _f(value) -> float:
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def monthly_cost_by_feature(year: int, month: int) -> pd.DataFrame:
    """
    Sum persisted AI cost for the given calendar month, grouped by feature.

    Returns columns: feature, cost_usd, calls — sorted by cost_usd descending.
    Features with no spend in the month are omitted; an empty month yields an
    empty frame with the correct columns.
    """
    prefix = f"{year:04d}-{month:02d}"

    db = SessionLocal()
    try:
        analyses = db.query(AIAnalysis).all()
        reviews = db.query(WeeklyReview).all()
    finally:
        db.close()

    rows = []

    ta_cost = 0.0
    ta_calls = 0
    for a in analyses:
        stamp = str(a.created_at or a.updated_at or "")
        if stamp.startswith(prefix):
            ta_cost += _f(a.cost_usd)
            ta_calls += 1
    if ta_calls:
        rows.append((_TRADE_ANALYSIS, round(ta_cost, 6), ta_calls))

    wr_cost = 0.0
    wr_calls = 0
    for r in reviews:
        if str(r.created_at or "").startswith(prefix):
            wr_cost += _f(r.cost_usd)
            wr_calls += 1
    if wr_calls:
        rows.append((_WEEKLY_REVIEW, round(wr_cost, 6), wr_calls))

    df = pd.DataFrame(rows, columns=_COST_COLS)
    if df.empty:
        return df
    return df.sort_values("cost_usd", ascending=False).reset_index(drop=True)
