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

import math
from datetime import datetime
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.json_schema import SkipJsonSchema

from src.tradelens.services.sessions import KILLZONE_LABELS
from src.tradelens.services.trade_validation import VALID_OUTCOMES

TradeResult = Literal["Win", "Loss", "Breakeven"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    @field_validator("result", mode="before", check_fields=False)
    @classmethod
    def _canonical_result(cls, value):
        """Normalize historical case without widening the public enum.

        The repository's seed path stored lowercase outcomes before canonical
        writes landed. Known spellings cross the wire canonically; an unknown
        value still fails the Literal instead of silently inventing meaning.
        """
        if value is None or not isinstance(value, str):
            return value
        return VALID_OUTCOMES.get(value.strip().lower(), value)


class TradeSummary(_Strict):
    """One row of the Trades list — deliberately narrower than TradeDetail.

    The list view does not need every SMC/ICT annotation field; Trade Detail
    (below) is where the full record lives.
    """

    id: int
    trade_date: Optional[str]
    asset: str
    direction: Optional[str]
    session: Optional[str]
    setup_type: Optional[str]
    killzone: Optional[str]
    result: Optional[TradeResult]
    pnl: Optional[float]
    rr_realized: Optional[float]

    # Spec §8 requires the trades table to show a grade and whether the row
    # has a screenshot. Those lived only on TradeDetail, so the list page had
    # to either omit two required columns or fabricate them from data the
    # endpoint does not return — and a fabricated column on a trader's
    # journal is wrong data, not a cosmetic gap.
    ai_grade: Optional[str]
    user_grade: Optional[str]

    # A count rather than a bool: the table renders an indicator either way,
    # and "3 screenshots" is strictly more useful than "yes" for deciding
    # which trade to open. It is also what justifies the
    # `selectinload(Trade.screenshots)` in `list_trades` — that eager load
    # reads as a wasted SELECT only while the summary has no screenshot
    # field, and without it this count would issue one query per row.
    screenshot_count: int


class TradeListResponse(_Strict):
    trades: List[TradeSummary]
    total: int
    limit: int
    offset: int


class TradeSummaryJobRequest(_Strict):
    """The filtered journal selection to summarize; ownership is never input."""

    from_: str = Field(alias="from")
    to: str
    asset: Optional[str] = None
    session: Optional[str] = None
    setup: Optional[str] = None
    result: Optional[str] = None


class TradeSummaryJobAccepted(_Strict):
    job_id: int
    status: Literal["queued", "running", "succeeded", "failed"]
    created: bool


class TradeSummaryResult(_Strict):
    content_md: str
    reviewed_trades: int


class TradeSummaryJobStatus(_Strict):
    job_id: int
    status: Literal["queued", "running", "succeeded", "failed"]
    result: Optional[TradeSummaryResult]
    error: Optional[str]


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
    asset: str
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
    updated_at: str

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
    `null` clears a nullable column. Those two are different intentions and the
    wire format can express both. `asset` is the exception because its database
    column is NOT NULL: it may be omitted, but it may not be sent as null.

    `expected_updated_at` is required, not optional. Inline editing on a page
    a trader may have left open invites the lost-update problem, and a guard
    a client can skip by omitting a field is not a guard.
    """

    expected_updated_at: str

    trade_date: Optional[str] = None
    # Optional to send, but never nullable when sent. SkipJsonSchema keeps the
    # runtime default honestly typed without advertising ``null`` in OpenAPI;
    # the validator rejects an explicit null while omission remains detectable
    # through exclude_unset=True.
    asset: Union[str, SkipJsonSchema[None]] = None
    session: Optional[str] = None
    setup_type: Optional[str] = None
    timeframe: Optional[str] = None
    direction: Optional[str] = None
    result: Optional[TradeResult] = None
    pnl: Optional[float] = None
    rr_realized: Optional[float] = None
    risk_amount: Optional[float] = None
    followed_rules: Optional[Literal[0, 1]] = None
    killzone: Optional[str] = None
    htf_bias: Optional[str] = None
    notes: Optional[str] = None
    mistake_tags: Optional[str] = None

    @field_validator("asset")
    @classmethod
    def _asset_must_exist_when_sent(cls, value: Optional[str]) -> str:
        # The ORM column is NOT NULL. Omission means leave it alone, but an
        # explicit null or blank would otherwise become either a 500 or a
        # stored trade no list/filter can identify.
        if value is None or not value.strip():
            raise ValueError("asset must not be blank")
        return value.strip()

    @field_validator("trade_date")
    @classmethod
    def _trade_date_must_be_iso_when_sent(cls, value: Optional[str]) -> Optional[str]:
        # Nullable legacy rows remain round-trippable. A non-null edit must be
        # one real calendar day, not merely a string shaped approximately like
        # one; day_of_week and period filtering derive from this value.
        if value is None:
            return None
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("trade_date must be a valid YYYY-MM-DD date") from exc
        if parsed.strftime("%Y-%m-%d") != value:
            raise ValueError("trade_date must be a valid YYYY-MM-DD date")
        return value

    @field_validator("pnl", "rr_realized", "risk_amount")
    @classmethod
    def _numbers_must_be_finite(cls, value: Optional[float]) -> Optional[float]:
        # Python's JSON decoder accepts values such as ``1e400`` as infinity.
        # SQLite may store that while PostgreSQL/strict serialization can fail
        # later, so reject it at the request boundary before any write occurs.
        if value is not None and not math.isfinite(value):
            raise ValueError("numeric values must be finite")
        return value

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

        **An unrecognised value passes through unchanged**, because the read
        contract emits unrecognised values unchanged: `_killzone_label` is
        `KILLZONE_LABELS.get(raw, raw)`, so a legacy row storing
        'legacy_zone' renders as 'legacy_zone'. Raising here made that trade
        readable and un-writable — and un-writable in ALL its fields, since
        an edit form posts the whole record, so a trader could not fix their
        notes on a row they never chose to annotate that way. The write must
        accept what the read emitted; the round trip is the contract.
        """
        if value is None:
            return None
        if value in KILLZONE_LABELS:
            return value
        for key, label in KILLZONE_LABELS.items():
            if value == label:
                return key
        return value


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
    current_updated_at: str


class TradeConflictResponse(_Strict):
    """The 409 body. Shaped to match FastAPI's `{"detail": ...}` envelope so
    the generated TypeScript describes what actually arrives."""

    detail: TradeConflictDetail


class ScreenshotCleanupFailedDetail(_Strict):
    """A delete that could not finish. The trade row is deliberately still
    there: a trader told their screenshots are gone while private images
    remain in the bucket has been given a false privacy assurance, so the
    state stays retryable rather than becoming an orphan nobody can find.

    `remaining` and `unresolvable` are separate numbers because they need
    different handling: `remaining` is an object-store fault that a retry
    will clear, while `unresolvable` counts screenshot rows naming a path
    this owner is not entitled to delete — a retry will never clear those,
    and the caller must be able to tell "try again" from "this needs an
    operator" rather than seeing one opaque total."""

    error: Literal["screenshot_cleanup_failed"]
    remaining: int
    unresolvable: int


class ScreenshotCleanupFailedResponse(_Strict):
    detail: ScreenshotCleanupFailedDetail
