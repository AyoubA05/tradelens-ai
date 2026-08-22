# src/tradelens/api/schemas/trades.py
"""The Trades list response contract.

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
    """One row of the Trades list — deliberately narrower than Trade Detail."""

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
