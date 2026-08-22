# src/tradelens/api/routers/trades.py
"""The Trades list and Trade Detail endpoints.

Thin by design, matching `routers/overview.py`: validate input, call the
service with the session's owner, shape the response. All filtering,
pagination and ownership live in `services/trade_service`; screenshot
ownership and presigning live in `services/storage` (via `services.storage`
imported as a module, not the bare function, so tests can patch it).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.tradelens.api import storage
from src.tradelens.api.deps import current_user
from src.tradelens.api.routers.overview import _validated_period
from src.tradelens.api.schemas.trades import (
    ScreenshotDescriptor,
    TradeDetail,
    TradeListResponse,
    TradeSummary,
)
from src.tradelens.services.sessions import KILLZONE_LABELS
from src.tradelens.services.trade_service import get_trade, list_trades

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


def _not_found() -> HTTPException:
    """One refusal for both 'no such trade' and 'someone else's trade'.

    A 403 would confirm the row exists for a different owner — a cross-tenant
    existence oracle. Both cases return this exact object so the responses
    are byte-identical.
    """
    return HTTPException(status_code=404, detail="trade not found")


@router.get("/trades/{trade_id}")
def get_trade_detail(
    trade_id: int,
    user_id: int = Depends(current_user),
) -> TradeDetail:
    """One trade, plus presigned URLs for its screenshots.

    `get_trade` already filters on `Trade.user_id == owner`, so a trade
    belonging to another account is indistinguishable from a nonexistent one
    at the ORM layer — this handler preserves that by raising the identical
    404 either way, never a 403.
    """
    trade = get_trade(trade_id, user_id)
    if trade is None:
        raise _not_found()

    screenshots = [
        ScreenshotDescriptor(
            id=shot.id,
            width=shot.width,
            height=shot.height,
            uploaded_at=shot.uploaded_at,
            url=storage.presign_download(user_id, shot.id),
        )
        for shot in trade.screenshots
    ]

    return TradeDetail(
        id=trade.id,
        trade_date=trade.trade_date,
        day_of_week=trade.day_of_week,
        session=trade.session,
        asset=trade.asset,
        asset_class=trade.asset_class,
        timeframe=trade.timeframe,
        direction=trade.direction,
        bias=trade.bias,
        setup_type=trade.setup_type,
        entry_price=trade.entry_price,
        stop_price=trade.stop_price,
        tp_price=trade.tp_price,
        exit_price=trade.exit_price,
        position_size=trade.position_size,
        risk_amount=trade.risk_amount,
        reward_amount=trade.reward_amount,
        rr_planned=trade.rr_planned,
        rr_realized=trade.rr_realized,
        result=trade.result,
        pnl=trade.pnl,
        strategy_used=trade.strategy_used,
        emotions_before=trade.emotions_before,
        emotions_during=trade.emotions_during,
        emotions_after=trade.emotions_after,
        notes=trade.notes,
        trade_process_notes=trade.trade_process_notes,
        ai_grade=trade.ai_grade,
        user_grade=trade.user_grade,
        htf_bias=trade.htf_bias,
        killzone=_killzone_label(trade.killzone),
        liquidity_sweep=trade.liquidity_sweep,
        fvg_used=trade.fvg_used,
        order_block_used=trade.order_block_used,
        bos=trade.bos,
        choch=trade.choch,
        confirmation_model=trade.confirmation_model,
        entry_type=trade.entry_type,
        mistake_tags=trade.mistake_tags,
        followed_rules=trade.followed_rules,
        created_at=trade.created_at,
        updated_at=trade.updated_at,
        screenshots=screenshots,
    )
