"""
AI cost observability.

Aggregates persisted AI spend for a calendar month, grouped by feature, for the
Settings cost dashboard. Cost comes from three places: ai_analysis (the
per-trade vision/journal/grading pipeline), weekly_reviews, and ai_usage_log
(per-call rows for features with no natural persistence row — the AI Partner
and pattern-card detection log through ``log_ai_usage``).

No Streamlit imports here.
"""

from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from src.tradelens.db.models import AIAnalysis, AIUsageLog, Trade, WeeklyReview
from src.tradelens.db.session import SessionLocal

_COST_COLS = ["feature", "cost_usd", "calls"]

_TRADE_ANALYSIS = "Trade Analysis (vision/journal/grading)"
_WEEKLY_REVIEW = "Weekly Review"


def _f(value) -> float:
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _require_concrete_user_id(user_id: int) -> int:
    """Return a concrete cost owner ID or reject ownerless access."""
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("user_id must be a positive integer")
    return user_id


def log_ai_usage(feature: str, usage, user_id: Optional[int] = None) -> None:
    """Persist one AI call's usage to ai_usage_log (best-effort; never raises).

    For features with no natural persistence row — the AI Partner chat and
    pattern-card detection. ``usage`` is an ai_client.Usage; None is ignored.
    """
    if usage is None or not feature:
        return
    try:
        db = SessionLocal()
        try:
            db.add(
                AIUsageLog(
                    feature=feature,
                    model=getattr(usage, "model", None),
                    tokens_input=getattr(usage, "tokens_in", None),
                    tokens_output=getattr(usage, "tokens_out", None),
                    cost_usd=getattr(usage, "estimated_cost_usd", None),
                    user_id=user_id,
                    created_at=datetime.now(timezone.utc).isoformat(),
                )
            )
            db.commit()
        finally:
            db.close()
    except Exception:  # noqa: BLE001 — telemetry must never break an AI feature
        return


def monthly_cost_by_feature(year: int, month: int, user_id: int) -> pd.DataFrame:
    """
    Sum persisted AI cost for the given calendar month, grouped by feature.

    Returns columns: feature, cost_usd, calls — sorted by cost_usd descending.
    Features with no spend in the month are omitted; an empty month yields an
    empty frame with the correct columns.
    """
    user_id = _require_concrete_user_id(user_id)
    prefix = f"{year:04d}-{month:02d}"

    db = SessionLocal()
    try:
        analyses = (
            db.query(AIAnalysis)
            .join(Trade, AIAnalysis.trade_id == Trade.id)
            .filter(Trade.user_id == user_id)
            .all()
        )
        reviews = db.query(WeeklyReview).filter(WeeklyReview.user_id == user_id).all()
        usage_rows = db.query(AIUsageLog).filter(AIUsageLog.user_id == user_id).all()
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

    # Per-call usage log (AI Partner, Pattern Detection, …) grouped by feature.
    by_feature: dict = {}
    for u in usage_rows:
        if str(u.created_at or "").startswith(prefix):
            cost, calls = by_feature.get(u.feature, (0.0, 0))
            by_feature[u.feature] = (cost + _f(u.cost_usd), calls + 1)
    for feature, (cost, calls) in sorted(by_feature.items()):
        rows.append((feature, round(cost, 6), calls))

    df = pd.DataFrame(rows, columns=_COST_COLS)
    if df.empty:
        return df
    return df.sort_values("cost_usd", ascending=False).reset_index(drop=True)
