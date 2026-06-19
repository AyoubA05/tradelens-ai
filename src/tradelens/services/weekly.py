"""
Weekly AI review service.

Gathers a Monday→Sunday window of trades, computes week stats + a deterministic
pattern pre-pass, folds in recent corrections as a few-shot block, and asks
claude-fable-5 (effort="high", thinking summarized) for a structured 5-section
review via prompts/weekly_v2.txt. Reviews persist to the weekly_reviews table;
re-running the same week overwrites only with explicit confirmation.

This is post-trade reflection only — never live signals, predictions, or advice.
No Streamlit imports here. DEMO_MODE returns a canned review (zero API spend).
"""

import datetime as dt
import json
import math
from typing import Optional, Union

import pandas as pd

from src.tradelens.db.models import WeeklyReview
from src.tradelens.db.session import SessionLocal
from src.tradelens.services.ai_client import AIUnavailable, Usage, chat, load_prompt
from src.tradelens.services.metrics import (
    compute_basic_metrics,
    compute_profit_factor_raw,
    total_edge_leak,
)
from src.tradelens.services.patterns import compute_candidates
from src.tradelens.services.trade_service import get_trades

_REQUIRED_SECTIONS = [
    "### What Worked",
    "### What Didn't",
    "### Killzone Review",
    "### Rule Adherence",
    "### Focus for Next Week",
]

# Columns the metrics/patterns engines expect from each trade row.
_TRADE_COLS = [
    "trade_date",
    "day_of_week",
    "result",
    "pnl",
    "rr_realized",
    "killzone",
    "confirmation_model",
    "mistake_tags",
    "htf_bias",
    "setup_type",
    "followed_rules",
]

# Canned review returned in DEMO_MODE (zero spend) — satisfies the 5-section contract.
_DEMO_REVIEW_MD = "\n\n".join(
    f"{h}\n\n_DEMO MODE_ — sample reflection for this section."
    for h in _REQUIRED_SECTIONS
)


class WeeklyReviewError(Exception):
    """Raised when the AI weekly review is unavailable or missing required sections."""


class WeeklyReviewExistsError(Exception):
    """Raised when saving a review for a week that already has one (without overwrite)."""


# ---------------------------------------------------------------------------
# Week window
# ---------------------------------------------------------------------------


def week_bounds(value: Union[str, dt.date, dt.datetime]) -> tuple:
    """Return (monday_iso, sunday_iso) for the ISO week containing `value`."""
    if isinstance(value, str):
        d = dt.date.fromisoformat(value[:10])
    elif isinstance(value, dt.datetime):
        d = value.date()
    else:
        d = value
    monday = d - dt.timedelta(days=d.weekday())
    sunday = monday + dt.timedelta(days=6)
    return monday.isoformat(), sunday.isoformat()


# ---------------------------------------------------------------------------
# Context assembly
# ---------------------------------------------------------------------------


def _trades_to_df(trades: list) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame(columns=_TRADE_COLS)
    return pd.DataFrame([{c: getattr(t, c, None) for c in _TRADE_COLS} for t in trades])


def _week_stats(df: pd.DataFrame) -> dict:
    """Headline week stats for the sidebar + persisted history. JSON-safe (no inf)."""
    if df is None or df.empty:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "profit_factor": None,
            "total_edge_leak": 0.0,
        }
    m = compute_basic_metrics(df)
    pf = compute_profit_factor_raw(df)
    return {
        "trades": int(m["total_trades"]),
        "win_rate": m["win_rate"],
        "total_pnl": m["total_pnl"],
        "profit_factor": None if math.isinf(pf) else pf,
        "total_edge_leak": total_edge_leak(df),
    }


def _build_user_message(monday: str, sunday: str, stats: dict, candidates: dict) -> str:
    return (
        "WEEKLY REVIEW REQUEST\n\n"
        f"Week: {monday} (Mon) to {sunday} (Sun)\n\n"
        f"Headline stats:\n{json.dumps(stats, indent=2, default=str)}\n\n"
        "Deterministic pattern statistics for the week:\n"
        f"{json.dumps(candidates, indent=2, default=str)}\n\n"
        "Write the 5-section weekly review now."
    )


def _validate_sections(markdown: str) -> None:
    positions = []
    for section in _REQUIRED_SECTIONS:
        idx = markdown.find(section)
        if idx == -1:
            raise WeeklyReviewError(
                f"Weekly review is missing required section: '{section}'"
            )
        positions.append(idx)
    if positions != sorted(positions):
        raise WeeklyReviewError("Weekly review sections are out of order.")


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def generate_weekly_review(
    week_start: Union[str, dt.date, dt.datetime],
) -> tuple[dict, Usage]:
    """
    Generate (but do not persist) the weekly review for the week containing
    `week_start`. A zero-trade week returns an empty result WITHOUT any API call.

    Returns (review_dict, usage). review_dict keys: week_start (ISO Monday),
    empty, content_md, thinking_summary, stats, cost_usd.

    Raises:
        FileNotFoundError: prompts/weekly_v2.txt missing.
        WeeklyReviewError: AI unavailable or response missing required sections.
    """
    monday, sunday = week_bounds(week_start)
    trades = get_trades(start_date=monday, end_date=sunday)
    df = _trades_to_df(trades)
    stats = _week_stats(df)

    if df.empty:
        return (
            {
                "week_start": monday,
                "empty": True,
                "content_md": None,
                "thinking_summary": None,
                "stats": stats,
                "cost_usd": 0.0,
            },
            Usage("none", 0, 0, 0, 0.0, 0.0),
        )

    candidates = compute_candidates(df)

    system_message = load_prompt("weekly_v2")
    user_message = _build_user_message(monday, sunday, stats, candidates)

    # Past corrections are injected centrally by ai_client for every call.
    content, usage = chat(
        user_message=user_message,
        system_message=system_message,
        effort="high",
        demo_response=_DEMO_REVIEW_MD,
    )

    if isinstance(content, AIUnavailable):
        raise WeeklyReviewError(content.reason)

    _validate_sections(content)
    return (
        {
            "week_start": monday,
            "empty": False,
            "content_md": content,
            "thinking_summary": usage.thinking_summary,
            "stats": stats,
            "cost_usd": usage.estimated_cost_usd,
        },
        usage,
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def _row_to_dict(row: WeeklyReview) -> dict:
    try:
        stats = json.loads(row.stats_json) if row.stats_json else {}
    except (json.JSONDecodeError, TypeError):
        stats = {}
    return {
        "id": row.id,
        "week_start": row.week_start,
        "content_md": row.content_md,
        "thinking_summary": row.thinking_summary,
        "stats": stats,
        "cost_usd": row.cost_usd,
        "created_at": row.created_at,
    }


def save_weekly_review(review: dict, overwrite: bool = False) -> dict:
    """
    Persist a generated review. If a review already exists for the same week_start
    and overwrite is False, raises WeeklyReviewExistsError (the page asks the user
    to confirm before retrying with overwrite=True). Returns the saved row as a dict.
    """
    week_start = review["week_start"]
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    db = SessionLocal()
    try:
        existing = (
            db.query(WeeklyReview).filter(WeeklyReview.week_start == week_start).first()
        )
        if existing is not None and not overwrite:
            raise WeeklyReviewExistsError(
                f"A review for the week of {week_start} already exists."
            )

        if existing is None:
            row = WeeklyReview(week_start=week_start, created_at=now)
            db.add(row)
        else:
            row = existing

        row.content_md = review.get("content_md")
        row.thinking_summary = review.get("thinking_summary")
        row.stats_json = json.dumps(review.get("stats") or {}, default=str)
        row.cost_usd = review.get("cost_usd")

        db.commit()
        db.refresh(row)
        return _row_to_dict(row)
    finally:
        db.close()


def get_weekly_review(week_start: str) -> Optional[dict]:
    """Return the persisted review for the given ISO Monday, or None."""
    db = SessionLocal()
    try:
        row = (
            db.query(WeeklyReview).filter(WeeklyReview.week_start == week_start).first()
        )
        return _row_to_dict(row) if row else None
    finally:
        db.close()


def list_weekly_reviews() -> list:
    """Return all persisted reviews as dicts, most recent week first."""
    db = SessionLocal()
    try:
        rows = (
            db.query(WeeklyReview)
            .order_by(WeeklyReview.week_start.desc(), WeeklyReview.id.desc())
            .all()
        )
        return [_row_to_dict(r) for r in rows]
    finally:
        db.close()
