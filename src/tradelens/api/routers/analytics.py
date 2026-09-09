"""`GET /v1/analytics` — the four lenses over one owner's filtered sample."""

from __future__ import annotations

from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from src.tradelens.api.deps import current_user
from src.tradelens.api.routers.overview import _validated_period
from src.tradelens.api.schemas.analytics import AnalyticsResponse
from src.tradelens.services import analytics
from src.tradelens.services.trade_service import get_trades

router = APIRouter(prefix="/v1", tags=["analytics"])


_KNOWN_QUERY_PARAMS = frozenset({"from", "to", "asset", "session", "strategy"})


def _refuse_unknown_params(request: Request) -> None:
    """Refuse a query parameter this endpoint does not implement.

    FastAPI ignores unrecognised query parameters, which on a filtered
    aggregate is the wrong default: a client sending `?setup=FVG` — a filter
    the journal DOES have — would get an unfiltered total back and no
    indication that its filter did nothing. The trader then reads a
    whole-period figure as a narrowed one.

    Refusing is the only answer that cannot mislead. Silently ignoring is
    the same failure as silently widening the date range.
    """
    unknown = sorted(set(request.query_params) - _KNOWN_QUERY_PARAMS)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail="unsupported query parameter(s): {}".format(", ".join(unknown)),
        )


@router.get("/analytics")
def get_analytics(
    request: Request,
    from_: str = Query(alias="from"),
    to: str = Query(),
    asset: Optional[str] = Query(default=None),
    session: Optional[str] = Query(default=None),
    strategy: Optional[str] = Query(default=None),
    user_id: int = Depends(current_user),
) -> AnalyticsResponse:
    """Every figure the four lenses need, for this owner and this window.

    The owner comes from the session and from nowhere else, and the period is
    validated rather than coerced: a range nothing can render is refused, not
    quietly widened into one that returns numbers the trader never asked for.

    The category filters are applied to the FRAME, not through
    `get_trades`' own `asset`/`strategy` arguments — those use
    `ilike('%..%')`, which would fold MNQ into an NQ trader's total. Dates go
    through `get_trades` because its date comparisons are exact.

    ONE filtered frame feeds every lens below. That is what makes the
    headline total and each breakdown describe the same sample rather than
    four samples that happen to look alike.
    """
    _refuse_unknown_params(request)
    start, end = _validated_period(from_, to)
    trades = get_trades(user_id=user_id, start_date=start, end_date=end)

    applied: Dict[str, str] = {}
    for name, value in (("asset", asset), ("session", session), ("strategy", strategy)):
        if value:
            applied[name] = value

    df = analytics.apply_filters(analytics.frame(trades), applied)

    return AnalyticsResponse(
        period={"from": start, "to": end},
        filters=applied,
        performance=analytics.build_performance(df),
        risk=analytics.build_risk(df),
        timing=analytics.build_timing(df),
        setups=analytics.build_setups(df),
        discipline=analytics.build_discipline(df),
    )
