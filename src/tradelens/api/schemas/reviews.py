"""Response and request models for `/v1/reviews` (Phase 10A).

Strict both ways: requests forbid extra fields and coercion, so no body can
name an owner, a trade id set or a review id; responses forbid extras so a
field added to a service dict cannot leak through unnoticed.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class PeriodStats(_Strict):
    trades: int
    win_rate: float
    total_pnl: float
    profit_factor: Optional[float] = None
    total_edge_leak: float
    financial_status: Literal["no_sample", "incomplete", "measured"]


class PatternInsight(_Strict):
    title: str
    body: str
    confidence: Literal["low", "medium", "high"]
    type: str
    min_trades: int


class PatternsLens(_Strict):
    trades: int
    stats: PeriodStats
    insights: List[PatternInsight]
    strategy_included: bool


class SavedNote(_Strict):
    period: str
    content_md: str
    stats: PeriodStats
    reviewed_trades: int
    created_at: str


class WeeklyRecapRequest(_Strict):
    week: str


class DailyDebriefRequest(_Strict):
    day: str


class ReviewJobAccepted(_Strict):
    job_id: int
    status: Literal["queued", "running", "succeeded", "failed"]
    created: bool


class ReviewJobStatus(_Strict):
    job_id: int
    kind: Literal["weekly_recap", "daily_debrief"]
    status: Literal["queued", "running", "succeeded", "failed", "superseded"]
    note: Optional[SavedNote] = None
    error: Optional[str] = None


class ReviewsResponse(_Strict):
    patterns: PatternsLens
    weeks: List[str]
    days: List[str]
    complete_trades: int
    trades_for_review: int
    ai_available: bool
    weekly: Optional[SavedNote] = None
    daily: Optional[SavedNote] = None
