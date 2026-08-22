# src/tradelens/api/schemas/trades.py
"""The Trades list and Trade Detail response contracts.

Matches `schemas/overview.py`'s hardened style: `strict=True`, `extra="forbid"`
so a service field this contract doesn't know about fails loudly rather than
vanishing from the response, and enum-likes as `Literal` rather than bare
`str`.

`killzone` is always the human label from `services.sessions.KILLZONE_LABELS`,
never the internal key ('ny_am' rather than 'New York AM') — that was a real
defect Codex caught in Phase 2's review, and this contract makes emitting the
raw key impossible to do by accident: there is no field named anything else a
future handler could reach for.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict

TradeResult = Literal["Win", "Loss", "Breakeven"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class TradeSummary(_Strict):
    """One row of the Trades list — deliberately narrower than TradeDetail.

    The list view does not need every SMC/ICT annotation field; Trade Detail
    (below) is where the full record lives.
    """

    id: int
    trade_date: Optional[str]
    asset: Optional[str]
    direction: Optional[str]
    session: Optional[str]
    setup_type: Optional[str]
    killzone: Optional[str]
    result: Optional[TradeResult]
    pnl: Optional[float]
    rr_realized: Optional[float]


class TradeListResponse(_Strict):
    trades: List[TradeSummary]
    total: int
    limit: int
    offset: int


class ScreenshotDescriptor(_Strict):
    """A screenshot with a short-lived presigned download URL.

    `url` is `None` when `presign_download` returned `None` for this object
    (rare — `finalize_upload` only ever stores a resolvable key) rather than
    surfacing an error; the caller simply has no image to render for that
    entry.
    """

    id: int
    width: Optional[int]
    height: Optional[int]
    uploaded_at: Optional[str]
    url: Optional[str]


class TradeDetail(_Strict):
    """The full trade record plus its screenshots.

    Server-owned and internal fields (`user_id`, `trade_hash`, `is_sample`,
    `strategy_id`) are deliberately absent — this is a read contract, not the
    ORM's column set, and none of those are anything a client should see or
    ever be able to round-trip back through a future PATCH.
    """

    id: int
    trade_date: Optional[str]
    day_of_week: Optional[str]
    session: Optional[str]
    asset: Optional[str]
    asset_class: Optional[str]
    timeframe: Optional[str]
    direction: Optional[str]
    bias: Optional[str]
    setup_type: Optional[str]

    entry_price: Optional[float]
    stop_price: Optional[float]
    tp_price: Optional[float]
    exit_price: Optional[float]
    position_size: Optional[float]
    risk_amount: Optional[float]
    reward_amount: Optional[float]

    rr_planned: Optional[float]
    rr_realized: Optional[float]

    result: Optional[TradeResult]
    pnl: Optional[float]

    strategy_used: Optional[str]
    emotions_before: Optional[str]
    emotions_during: Optional[str]
    emotions_after: Optional[str]
    notes: Optional[str]
    trade_process_notes: Optional[str]

    ai_grade: Optional[str]
    user_grade: Optional[str]

    htf_bias: Optional[str]
    killzone: Optional[str]
    liquidity_sweep: Optional[int]
    fvg_used: Optional[int]
    order_block_used: Optional[int]
    bos: Optional[int]
    choch: Optional[int]
    confirmation_model: Optional[str]
    entry_type: Optional[str]
    mistake_tags: Optional[str]
    followed_rules: Optional[int]

    created_at: Optional[str]
    updated_at: Optional[str]

    screenshots: List[ScreenshotDescriptor]
