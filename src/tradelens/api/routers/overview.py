# src/tradelens/api/routers/overview.py
"""The Overview endpoint.

Thin by design: validate the period, call the service with the session's owner,
return. All arithmetic lives in `services/overview`, and all ownership lives in
the services beneath it.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Tuple

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, HTTPException, Query

from src.tradelens.api.deps import current_user
from src.tradelens.api.schemas.overview import OverviewResponse
from src.tradelens.api.serialization import to_jsonable
from src.tradelens.services.overview import build_overview

router = APIRouter(prefix="/v1", tags=["overview"])

_MAX_WINDOW_YEARS = 5


def _validated_period(start: str, end: str) -> Tuple[str, str]:
    """Parse and order the range, or refuse it.

    The HMAC already covers the query, so this cannot be edited in transit —
    but an authenticated caller can still send a range that means nothing, and
    a window nothing can render is worse than a refusal.

    `date.fromisoformat` alone is not a strict-enough gate: Python 3.11 (CI and
    the container) also accepts compact ("20260201") and datetime-suffixed
    ("2026-02-01T00:00:00") forms that Python 3.9 (the local floor) rejects, so
    the two runtimes would disagree about what returns 422. The regex
    pre-check pins both to the same YYYY-MM-DD grammar before `fromisoformat`
    ever sees the value.
    """
    if not (
        re.fullmatch(r"\d{4}-\d{2}-\d{2}", start)
        and re.fullmatch(r"\d{4}-\d{2}-\d{2}", end)
    ):
        raise HTTPException(status_code=422, detail="period must be two ISO dates")
    try:
        first = dt.date.fromisoformat(start)
        last = dt.date.fromisoformat(end)
    except ValueError:
        raise HTTPException(
            status_code=422, detail="period must be two ISO dates"
        ) from None
    if first > last:
        raise HTTPException(status_code=422, detail="period start is after its end")
    if last > first + relativedelta(years=_MAX_WINDOW_YEARS):
        raise HTTPException(
            status_code=422,
            detail=f"period cannot span more than {_MAX_WINDOW_YEARS} years",
        )
    return first.isoformat(), last.isoformat()


@router.get("/overview")
def get_overview(
    from_: str = Query(..., alias="from"),
    to: str = Query(...),
    user_id: int = Depends(current_user),
) -> OverviewResponse:
    """Everything the Overview screen shows, for the authenticated owner.

    The owner is the session row's. Nothing in the query, the headers, or the
    body can name a different account.
    """
    start, end = _validated_period(from_, to)
    payload = to_jsonable(build_overview(user_id=user_id, start=start, end=end))
    payload["period"] = {"from_": start, "to": end}
    return OverviewResponse.model_validate(payload)
