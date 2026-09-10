"""`/v1/strategy` — the trader's playbook, the rulebook every AI review reads.

The profile is an owner-singleton: no route takes an id, and no request body
names an owner, a row or an active flag. The owner is the session.

Every route answers with the same `StrategyResponse`, built by `_response`,
so a write never returns a differently shaped (or differently computed)
picture than the page's own read.

Status mapping, fixed and never carrying exception text:

* 409 `stale_profile` — the profile changed since the caller read it; nothing
  was written.
* 409 `no_profile` / `rules_full` — an insight cannot be added; nothing written.
* 404 — no current repeated correction of THIS owner matches. The same bytes
  whether the group belongs to someone else, is below threshold, or never
  existed.
* 422 — a field problem, named by field and a fixed code, never by value.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from src.tradelens.api.deps import current_user
from src.tradelens.api.schemas.strategy import (
    StrategyFacets,
    StrategyFields,
    StrategyInsightRequest,
    StrategyLimits,
    StrategyResponse,
    StrategySection,
    StrategySuggestion,
    StrategyWrite,
)
from src.tradelens.services import strategy_writes
from src.tradelens.services.strategy import (
    _PROFILE_FIELDS,
    get_active_strategy,
    parse_markets,
    parse_setups,
    parse_timeframes,
)
from src.tradelens.services.strategy_playbook import (
    STARTER_TEMPLATE,
    profile_completion,
    section_status,
)
from src.tradelens.services.users import get_onboarding_state

router = APIRouter(prefix="/v1", tags=["strategy"])


def _fields(source: Optional[dict]) -> StrategyFields:
    return StrategyFields(**{f: (source or {}).get(f) for f in sorted(_PROFILE_FIELDS)})


def _response(owner: int) -> StrategyResponse:
    profile = get_active_strategy(owner)
    shown = profile or {}
    written, total = profile_completion(shown)
    timeframes = parse_timeframes(shown)
    return StrategyResponse(
        profile=_fields(profile) if profile is not None else None,
        revision=strategy_writes.profile_revision(profile),
        updated_at=shown.get("updated_at"),
        sections=[
            StrategySection(id=section_id, label=label, written=done)
            for section_id, label, done in section_status(shown)
        ],
        written=written,
        total=total,
        facets=StrategyFacets(
            markets=parse_markets(shown),
            entry_timeframe=timeframes.get("entry"),
            htf_timeframe=timeframes.get("htf"),
            setups=parse_setups(shown),
        ),
        over_limit=strategy_writes.over_limit(profile),
        limits=StrategyLimits(**dict(strategy_writes.FIELD_LIMITS)),
        starter=_fields(dict(STARTER_TEMPLATE)),
        suggestions=[
            StrategySuggestion(**s)
            for s in strategy_writes.insight_suggestions(owner, profile)
        ],
        first_run=not get_onboarding_state(owner)["strategy_profile_completed"],
    )


def _conflict(code: str) -> HTTPException:
    return HTTPException(status_code=409, detail=code)


def _invalid(exc: strategy_writes.InvalidProfile) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "detail": [
                {"field": field, "problem": problem}
                for field, problem in sorted(exc.problems.items())
            ]
        },
    )


@router.get("/strategy")
def get_strategy(user_id: int = Depends(current_user)) -> StrategyResponse:
    """The active playbook, its completion, the starter template and suggestions."""
    return _response(user_id)


@router.put("/strategy", response_model=StrategyResponse, responses={409: {}, 422: {}})
def put_strategy(payload: StrategyWrite, user_id: int = Depends(current_user)):
    """Replace the whole playbook, compared against the version it was edited from.

    Saving is also what completes the first-run step, in the same transaction.
    `response_model` is declared explicitly because the 422 path returns a
    `JSONResponse` directly; without it the generated TypeScript type for a
    successful save would be untyped.
    """
    fields = payload.model_dump()
    expected = fields.pop("expected_revision")
    try:
        strategy_writes.save_profile(user_id, fields, expected_revision=expected)
    except strategy_writes.InvalidProfile as exc:
        return _invalid(exc)
    except strategy_writes.StaleProfile:
        raise _conflict("stale_profile")
    return _response(user_id)


@router.post("/strategy/skip")
def skip_strategy(user_id: int = Depends(current_user)) -> StrategyResponse:
    """The first-run exit for a trader with no written rules yet.

    Completes first run and writes no profile — a playbook the trader did not
    write is never invented on their behalf.
    """
    strategy_writes.skip_first_run(user_id)
    return _response(user_id)


@router.post("/strategy/insights", responses={404: {}, 409: {}})
def add_strategy_insight(
    payload: StrategyInsightRequest, user_id: int = Depends(current_user)
) -> StrategyResponse:
    """Add one repeated correction to risk rules. Owner-scoped and idempotent."""
    try:
        strategy_writes.append_repeated_correction(
            user_id,
            field=payload.field,
            user_value=payload.user_value,
            expected_revision=payload.expected_revision,
        )
    except strategy_writes.SuggestionNotFound:
        raise HTTPException(status_code=404, detail="Not Found")
    except strategy_writes.NoProfile:
        raise _conflict("no_profile")
    except strategy_writes.RulesFull:
        raise _conflict("rules_full")
    except strategy_writes.StaleProfile:
        raise _conflict("stale_profile")
    return _response(user_id)
