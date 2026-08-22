# src/tradelens/api/routers/trades.py
"""The Trades list endpoint.

Thin by design, matching `routers/overview.py`: validate input, call the
service with the session's owner, shape the response. All filtering,
pagination and ownership live in `services/trade_service`.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from src.tradelens.api.deps import current_user
from src.tradelens.api.routers.overview import _validated_period
from src.tradelens.api.schemas.trades import TradeListResponse, TradeSummary
from src.tradelens.services.sessions import KILLZONE_LABELS
from src.tradelens.services.trade_service import list_trades

router = APIRouter(prefix="/v1", tags=["trades"])


def _killzone_label(raw: Optional[str]) -> Optional[str]:
    """The human label for a stored killzone key, or the raw value if unknown.

    Never the bare key for a value KILLZONE_LABELS does recognise — that was
    the Phase 2 defect Codex caught. An unrecognised value (e.g. legacy data
    predating the killzone engine) falls back to itself rather than raising,
    since a fully-typed response is still owed for rows the engine never
    touched.
    """
    if raw is None:
        return None
    return KILLZONE_LABELS.get(raw, raw)


@router.get("/trades")
def get_trades_list(
    from_: str = Query(..., alias="from"),
    to: str = Query(...),
    asset: Optional[str] = Query(None),
    session: Optional[str] = Query(None),
    setup: Optional[str] = Query(None),
    result: Optional[str] = Query(None),
    limit: int = Query(50),
    offset: int = Query(0),
    user_id: int = Depends(current_user),
) -> TradeListResponse:
    """The Trades list for the authenticated owner.

    The owner is the session row's, never the query. `limit`/`offset` are
    clamped inside `list_trades` itself, so a caller requesting `limit=1000`
    gets 100 back rather than a 422 — the service is the one source of truth
    for the bound, matching `list_trades`'s own contract.
    """
    start, end = _validated_period(from_, to)
    page = list_trades(
        user_id=user_id,
        start_date=start,
        end_date=end,
        asset=asset,
        session=session,
        setup_type=setup,
        result=result,
        limit=limit,
        offset=offset,
    )
    trades = [
        TradeSummary(
            id=trade.id,
            trade_date=trade.trade_date,
            asset=trade.asset,
            direction=trade.direction,
            session=trade.session,
            setup_type=trade.setup_type,
            killzone=_killzone_label(trade.killzone),
            result=trade.result,
            pnl=trade.pnl,
            rr_realized=trade.rr_realized,
        )
        for trade in page.trades
    ]
    return TradeListResponse(
        trades=trades, total=page.total, limit=page.limit, offset=page.offset
    )
