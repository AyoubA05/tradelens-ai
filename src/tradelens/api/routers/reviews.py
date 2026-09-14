"""`/v1/reviews` — AI Reviews: Patterns, review periods, saved notes.

Thin by design: validate input, call services with the session's owner, shape
the response. Patterns are deterministic (`patterns.generate_insights`, R9) and
need no AI. Every day/week boundary follows the owner's timezone through
`app_settings.today_for_owner` (C6).
"""

from __future__ import annotations

import datetime as dt
import math
import re
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from src.tradelens.api.deps import current_user
from src.tradelens.api.schemas.reviews import (
    PatternInsight,
    PatternsLens,
    PeriodStats,
    ReviewsResponse,
    SavedNote,
)
from src.tradelens.services import (
    activation,
    app_settings,
    daily_debriefs,
    patterns,
    review_periods,
    weekly,
)
from src.tradelens.services.demo import is_demo
from src.tradelens.services.strategy import get_active_strategy
from src.tradelens.services.trade_service import get_trades
from src.tradelens.utils.ai_utils import is_ai_enabled

router = APIRouter(prefix="/v1", tags=["reviews"])

_KNOWN = frozenset({"week", "day"})
_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")

# Copied verbatim from `ui/pages/6_Insights.py::_DF_COLS` (parity reference).
PATTERN_COLUMNS = [
    "id",
    "trade_date",
    "day_of_week",
    "session",
    "asset",
    "setup_type",
    "rr_realized",
    "pnl",
    "result",
    "killzone",
    "confirmation_model",
    "mistake_tags",
    "htf_bias",
    "direction",
    "followed_rules",
]


def _now_utc() -> dt.datetime:
    """The current instant. A seam so tests can pin 'today' across DST."""
    return dt.datetime.now(dt.timezone.utc)


def _today(owner: int) -> dt.date:
    return app_settings.today_for_owner(owner, now_utc=_now_utc())


def _iso_date(value: Optional[str], *, monday: bool = False) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str) or not _ISO.fullmatch(value):
        raise HTTPException(status_code=422, detail="dates must be ISO YYYY-MM-DD")
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError:
        raise HTTPException(
            status_code=422, detail="dates must be ISO YYYY-MM-DD"
        ) from None
    if monday and parsed.weekday() != 0:
        raise HTTPException(status_code=422, detail="week must be a Monday")
    return parsed.isoformat()


def _finite(value) -> float:
    number = float(value or 0.0)
    return number if math.isfinite(number) else 0.0


def _stats(raw: Optional[dict]) -> PeriodStats:
    raw = raw or {}
    pf = raw.get("profit_factor")
    pf = None if pf is None or not math.isfinite(float(pf)) else float(pf)
    return PeriodStats(
        trades=int(raw.get("trades") or 0),
        win_rate=_finite(raw.get("win_rate")),
        total_pnl=_finite(raw.get("total_pnl")),
        profit_factor=pf,
        total_edge_leak=_finite(raw.get("total_edge_leak")),
    )


def _note(saved: Optional[dict], key: str) -> Optional[SavedNote]:
    if saved is None or not saved.get("content_md"):
        return None
    stats = saved.get("stats") or {}
    return SavedNote(
        period=str(saved[key]),
        content_md=str(saved["content_md"]),
        stats=_stats(stats),
        reviewed_trades=int(stats.get("trades") or saved.get("reviewed_trades") or 0),
        created_at=str(saved["created_at"]),
    )


def _insight(raw: dict) -> PatternInsight:
    return PatternInsight(
        title=str(raw["title"]),
        body=str(raw["body"]),
        confidence=raw["confidence"],
        type=str(raw["type"]),
        min_trades=int(raw["min_trades"]),
    )


@router.get("/reviews")
def get_reviews(
    request: Request,
    week: Optional[str] = Query(default=None),
    day: Optional[str] = Query(default=None),
    user_id: int = Depends(current_user),
) -> ReviewsResponse:
    """Patterns, the owner's completed review periods, and saved notes."""
    if set(request.query_params) - _KNOWN:
        raise HTTPException(status_code=422, detail="unsupported query parameter(s)")
    week_iso, day_iso = _iso_date(week, monday=True), _iso_date(day)
    today = _today(user_id)
    trades = get_trades(user_id=user_id)
    frame = pd.DataFrame(
        [{c: getattr(t, c, None) for c in PATTERN_COLUMNS} for t in trades]
    )
    if not frame.empty:
        frame = frame[
            frame["trade_date"].notna() & (frame["trade_date"] != "")
        ].reset_index(drop=True)
    strategy = get_active_strategy(user_id)
    saved_week = weekly.get_weekly_review(week_iso, user_id) if week_iso else None
    saved_day = (
        daily_debriefs.get_daily_debrief(user_id=user_id, day=day_iso)
        if day_iso
        else None
    )
    return ReviewsResponse(
        patterns=PatternsLens(
            trades=len(frame),
            stats=_stats(review_periods.period_stats(frame)),
            insights=[_insight(i) for i in patterns.generate_insights(frame, strategy)],
            strategy_included=strategy is not None,
        ),
        weeks=[
            d.isoformat()
            for d in review_periods.completed_week_options(user_id, today=today)
        ],
        days=[
            d.isoformat()
            for d in review_periods.completed_day_options(user_id, today=today)
        ],
        complete_trades=sum(1 for t in trades if activation.is_complete_trade(t)),
        trades_for_review=activation.TRADES_FOR_REVIEW,
        ai_available=bool(is_ai_enabled() or is_demo()),
        weekly=_note(saved_week, "week_start"),
        daily=_note(saved_day, "day"),
    )
