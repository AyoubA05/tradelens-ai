"""The effective-input fingerprint for job-backed reviews (decision C2).

One digest names everything that can change a weekly recap or daily debrief:

* the job kind, the owner and the period;
* the exact model input object the service turns into the user message
  (`weekly.build_weekly_model_input` / `debrief.build_daily_model_input` —
  stats, pattern candidates, trade fields, truncated notes, the Strategy
  Profile block and the source trade ids);
* the prompt version: its file name plus the sha256 of the text exactly as
  `ai_client.load_prompt` returns it;
* the call's effort literal (`weekly.WEEKLY_EFFORT`, `debrief.DAILY_EFFORT`);
* `trade_analysis.ai_input_version(owner)` — model id, default effort, demo
  mode, the Strategy Profile and the correction memory.

The router keys the job with it, and the worker recomputes it before the
provider call and again inside the locked save (C3). Any change → a new key
and a new job; a stale job saves nothing.

`AIInputVersionUnavailable` propagates: callers refuse rather than guess.

Streamlit-free.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import math
from typing import Any, List, Optional

from sqlalchemy.orm import Session

from src.tradelens.db.models import Trade
from src.tradelens.services.ownership import require_user_id

# The prompt each kind's service loads. Must match the literal passed to
# `load_prompt(...)` in the service (the system-message sweep pins literals).
_PROMPTS = {
    "weekly_recap": "weekly_recap_v1",
    "daily_debrief": "debrief_v1",
}


def _effort(kind: str):
    # Read at call time so the fingerprint follows the constant the service uses.
    if kind == "weekly_recap":
        from src.tradelens.services import weekly

        return weekly.WEEKLY_EFFORT
    from src.tradelens.services import debrief

    return debrief.DAILY_EFFORT


def _canonical(value: Any) -> Any:
    """JSON-safe, deterministic form: non-finite floats become tagged strings."""
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if hasattr(value, "item") and not isinstance(value, (int, float)):
        try:
            value = value.item()  # numpy scalar
        except (TypeError, ValueError):
            return str(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value) if math.isfinite(value) else "__float__:" + repr(value)
    return str(value)


def review_corrections_block(owner: int) -> str:
    """Capture the exact owner-scoped correction text a review will send."""
    from src.tradelens.services import trade_analysis
    from src.tradelens.services.corrections import build_correction_few_shot

    try:
        return build_correction_few_shot(user_id=require_user_id(owner)) or ""
    except Exception as exc:  # noqa: BLE001 — fail closed on cache identity
        raise trade_analysis.AIInputVersionUnavailable(
            "the AI context could not be read"
        ) from exc


def review_input_fingerprint(
    kind: str,
    owner: int,
    period: str,
    model_input,
    *,
    corrections_block: Optional[str] = None,
) -> str:
    """sha256 hex over the canonical JSON of every effective review input."""
    from src.tradelens.services import ai_client, trade_analysis

    if kind not in _PROMPTS:
        raise ValueError("unknown review kind")
    resolved = require_user_id(owner)
    prompt_name = _PROMPTS[kind]
    prompt_text = ai_client.load_prompt(prompt_name)
    document = {
        "kind": kind,
        "owner": resolved,
        "period": str(period),
        "model_input": _canonical(model_input),
        "prompt": {
            "name": prompt_name,
            "sha256": hashlib.sha256(prompt_text.encode("utf-8")).hexdigest(),
        },
        "effort": _effort(kind),
        "ai_input_version": trade_analysis.ai_input_version(
            resolved,
            **(
                {}
                if corrections_block is None
                else {
                    "corrections_fingerprint": hashlib.sha256(
                        corrections_block.encode("utf-8")
                    ).hexdigest()[:16]
                }
            ),
        ),
    }
    canonical = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _now_utc() -> datetime.datetime:
    """The current instant. A seam so tests can pin 'today' across DST."""
    return datetime.datetime.now(datetime.timezone.utc)


def review_as_of(
    owner: int, *, now_utc: Optional[datetime.datetime] = None
) -> datetime.date:
    """The one "as of today" rule for review input (decision C6).

    The owner's local calendar date via `app_settings.today_for_owner`. The
    router's enqueue, the worker's pre-provider recompute and its locked
    verify all resolve it here and pass it as `as_of`, so on the same owner
    day they build the same input. `as_of` is deliberately not fingerprinted:
    a job stays valid across midnight unless the set of eligible trades
    changes — and when a later-dated trade in the period becomes eligible,
    the recomputed input differs and the job is superseded.
    """
    from src.tradelens.services import app_settings

    return app_settings.today_for_owner(
        require_user_id(owner), now_utc=now_utc or _now_utc()
    )


def on_or_before(trades: list, as_of: datetime.date) -> list:
    """Trades whose date is on or before `as_of`; future-dated rows are dropped."""
    cutoff = as_of.isoformat()
    return [t for t in trades if str(getattr(t, "trade_date", "") or "")[:10] <= cutoff]


def locked_period_trades(db: Session, owner: int, start: str, end: str) -> List[Trade]:
    """The owner's trades in [start, end], read through the locking session.

    Same filters as `trade_service.get_trades(start_date=, end_date=)`, so the
    in-transaction recompute sees the rows the save has locked.
    """
    resolved = require_user_id(owner)
    return (
        db.query(Trade)
        .filter(
            Trade.user_id == resolved,
            Trade.trade_date >= start,
            Trade.trade_date <= end,
        )
        .order_by(Trade.trade_date.desc())
        .all()
    )
