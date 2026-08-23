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

from pydantic import BaseModel, ConfigDict, field_validator

from src.tradelens.services.sessions import KILLZONE_LABELS

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


class TradeUpdate(_Strict):
    """The PATCH body — a POSITIVE allowlist of genuinely user-editable fields.

    `trade_service.update_trade` accepts every column except `id` and
    `user_id`. That is right for a trusted in-process caller and wrong at an
    HTTP edge, so this model names the editable fields and nothing else;
    `extra="forbid"` refuses the rest. Ownership and server-owned metadata —
    `user_id`, `id`, `trade_hash`, `is_sample`, `created_at`, `updated_at`,
    `strategy_id` — are therefore unreachable through HTTP input whatever the
    request says.

    Because the allowlist is positive, a new column on the `Trade` model is
    NOT editable until someone deliberately adds it here. The safe default
    survives schema growth, and `SERVER_OWNED_TRADE_COLUMNS` below makes that
    growth visible: a column in neither set fails the contract test.

    Every field defaults to unset, and the handler dumps with
    `exclude_unset=True`, so an omitted field is left alone while an explicit
    `null` clears the column. Those two are different intentions and the wire
    format can express both.

    `expected_updated_at` is required, not optional. Inline editing on a page
    a trader may have left open invites the lost-update problem, and a guard
    a client can skip by omitting a field is not a guard.
    """

    expected_updated_at: str

    trade_date: Optional[str] = None
    asset: Optional[str] = None
    session: Optional[str] = None
    setup_type: Optional[str] = None
    timeframe: Optional[str] = None
    direction: Optional[str] = None
    result: Optional[TradeResult] = None
    pnl: Optional[float] = None
    rr_realized: Optional[float] = None
    risk_amount: Optional[float] = None
    followed_rules: Optional[int] = None
    killzone: Optional[str] = None
    htf_bias: Optional[str] = None
    notes: Optional[str] = None
    mistake_tags: Optional[str] = None

    @field_validator("killzone")
    @classmethod
    def _killzone_to_storage_key(cls, value: Optional[str]) -> Optional[str]:
        """Accept what the read contract emits, store what the engine uses.

        `TradeDetail.killzone` is always the human label, so a client that
        reads a trade and writes it back sends a label. Storing that verbatim
        would put 'New York AM' in a column the killzone engine matches on
        'ny_am', quietly breaking every session filter for the edited row.
        The storage key is also accepted so an already-normalised client is
        not punished for being correct.
        """
        if value is None:
            return None
        if value in KILLZONE_LABELS:
            return value
        for key, label in KILLZONE_LABELS.items():
            if value == label:
                return key
        raise ValueError(f"unknown killzone: {value!r}")


# The write surface, derived from the model itself so the two cannot drift.
EDITABLE_TRADE_FIELDS = frozenset(TradeUpdate.model_fields) - {"expected_updated_at"}

# Every remaining `Trade` column, named explicitly. This is not decoration:
# a column added to the model belongs to neither set until someone files it,
# and the contract test fails until they do — so schema growth cannot widen
# what HTTP can write by accident.
SERVER_OWNED_TRADE_COLUMNS = frozenset(
    {
        "id",
        "user_id",
        "trade_hash",
        "is_sample",
        "created_at",
        "updated_at",
        "strategy_id",
        "day_of_week",
        "asset_class",
        "bias",
        "entry_price",
        "stop_price",
        "tp_price",
        "exit_price",
        "position_size",
        "reward_amount",
        "rr_planned",
        "strategy_used",
        "emotions_before",
        "emotions_during",
        "emotions_after",
        "trade_process_notes",
        "ai_grade",
        "user_grade",
        "liquidity_sweep",
        "fvg_used",
        "order_block_used",
        "bos",
        "choch",
        "confirmation_model",
        "entry_type",
    }
)


class TradeConflictDetail(_Strict):
    """What the client needs to show a trader whose edit lost a race."""

    error: Literal["stale_trade"]
    current_updated_at: Optional[str]


class TradeConflictResponse(_Strict):
    """The 409 body. Shaped to match FastAPI's `{"detail": ...}` envelope so
    the generated TypeScript describes what actually arrives."""

    detail: TradeConflictDetail


class ScreenshotCleanupFailedDetail(_Strict):
    """A delete that could not finish. The trade row is deliberately still
    there: a trader told their screenshots are gone while private images
    remain in the bucket has been given a false privacy assurance, so the
    state stays retryable rather than becoming an orphan nobody can find."""

    error: Literal["screenshot_cleanup_failed"]
    remaining: int


class ScreenshotCleanupFailedResponse(_Strict):
    detail: ScreenshotCleanupFailedDetail
