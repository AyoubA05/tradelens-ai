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
from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema

from src.tradelens.services.sessions import KILLZONE_LABELS, parse_time_input
from src.tradelens.services.trade_validation import VALID_OUTCOMES

TradeResult = Literal["Win", "Loss", "Breakeven"]


def _suggestable_fields() -> frozenset:
    """The autofill write allowlist, resolved lazily.

    Imported inside the function rather than at module scope so this schema
    module stays importable from anywhere in the service layer: the autofill
    service is the one place the allowlist is *defined*, and a module-level
    import here would make the two mutually dependent.
    """
    from src.tradelens.services.trade_autofill import AUTOFILL_SUGGESTION_FIELDS

    return AUTOFILL_SUGGESTION_FIELDS


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


class AutofillSuggestion(_Strict):
    """One AI-suggested value for one draft field, with its confidence.

    A suggestion is deliberately NOT the field's value. It is provenance-
    tagged metadata that sits beside the draft, so an unreviewed suggestion
    stays distinguishable from something the trader typed right up until they
    accept it — which is the whole difference between assistive and
    authoritative.

    `autocheck` is not a second confidence policy: it is whatever
    `ui.components.ai_autofill_review.should_autocheck` decided, carried on
    the wire so the browser and Streamlit pre-check the same boxes.
    """

    value: Union[str, float, int, None] = None
    confidence: Optional[float] = None
    autocheck: bool = False


class TradeAutofillJobRequest(_Strict):
    """Which of the caller's own screenshots to read. Ownership is never input.

    A screenshot id, not a key and not a URL: the bytes autofill analyses are
    the promoted object `finalize_upload` produced, and this is the only
    handle the browser has on one.
    """

    screenshot_id: int


class TradeAutofillJobAccepted(_Strict):
    job_id: int
    status: Literal["queued", "running", "succeeded", "failed"]
    created: bool


class TradeAutofillJobStatus(_Strict):
    """Poll response. `suggestions` is `None` until the job has succeeded."""

    job_id: int
    status: Literal["queued", "running", "succeeded", "failed"]
    suggestions: Optional[Dict[str, AutofillSuggestion]]
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


class TradeCreate(_Strict):
    """`POST /v1/trades` body — a POSITIVE allowlist, same discipline as
    `TradeUpdate`. Ownership, idempotency, derived analytics and other
    server-owned metadata are unreachable through HTTP input;
    `extra="forbid"` refuses anything else, including a new `Trade` column
    that has not been deliberately filed here.

    Mirrors the field set the Streamlit New Trade page (`1_NewTrade.py`)
    actually submits to `create_trade`, minus what the service derives itself
    (`day_of_week`, `session`, `killzone`, `asset_class`, `strategy_used`,
    `rr_planned`, `ai_grade`, `user_grade`) and minus the other server-owned
    columns. `entry_time` is not a `Trade` column — it feeds derivation and
    `compute_trade_hash` — but is accepted here because omitting it would
    silently change the fingerprint the client and server agree on.
    """

    trade_date: str
    asset: str
    entry_time: str
    direction: Optional[str] = None
    bias: Optional[str] = None
    setup_type: Optional[str] = None
    timeframe: Optional[str] = None
    htf_bias: Optional[str] = None
    confirmation_model: Optional[str] = None
    entry_type: Optional[str] = None

    entry_price: Optional[float] = None
    stop_price: Optional[float] = None
    tp_price: Optional[float] = None
    exit_price: Optional[float] = None
    position_size: Optional[float] = None
    risk_amount: Optional[float] = None
    reward_amount: Optional[float] = None
    rr_realized: Optional[float] = None

    result: Optional[TradeResult] = None
    pnl: Optional[float] = None

    liquidity_sweep: Optional[Literal[0, 1]] = None
    fvg_used: Optional[Literal[0, 1]] = None
    order_block_used: Optional[Literal[0, 1]] = None
    bos: Optional[Literal[0, 1]] = None
    choch: Optional[Literal[0, 1]] = None
    followed_rules: Optional[Literal[0, 1]] = None
    mistake_tags: Optional[str] = None

    emotions_before: Optional[str] = None
    emotions_during: Optional[str] = None
    emotions_after: Optional[str] = None
    notes: Optional[str] = None
    trade_process_notes: Optional[str] = None

    @field_validator("asset")
    @classmethod
    def _asset_must_not_be_blank(cls, value: str) -> str:
        # The ORM column is NOT NULL; a blank string would be a stored trade
        # no list/filter can identify.
        if not value.strip():
            raise ValueError("asset must not be blank")
        return value.strip()

    @field_validator("trade_date")
    @classmethod
    def _trade_date_must_be_iso(cls, value: str) -> str:
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("trade_date must be a valid YYYY-MM-DD date") from exc
        if parsed.strftime("%Y-%m-%d") != value:
            raise ValueError("trade_date must be a valid YYYY-MM-DD date")
        return value

    @field_validator("entry_time")
    @classmethod
    def _entry_time_must_be_readable(cls, value: str) -> str:
        parsed = parse_time_input(value)
        if parsed is None:
            raise ValueError("entry_time must be a readable time")
        # Streamlit passes a datetime.time into compute_trade_hash, whose
        # stable string form includes seconds. Canonicalising the HTTP spelling
        # to the same representation preserves duplicate detection across the
        # two live application surfaces.
        return parsed.strftime("%H:%M:%S")

    @model_validator(mode="after")
    def _entry_and_stop_must_differ(self):
        if (
            self.entry_price is not None
            and self.stop_price is not None
            and self.entry_price == self.stop_price
        ):
            raise ValueError("entry_price and stop_price must differ")
        return self

    @field_validator(
        "pnl",
        "rr_realized",
        "risk_amount",
        "reward_amount",
        "entry_price",
        "stop_price",
        "tp_price",
        "exit_price",
        "position_size",
    )
    @classmethod
    def _numbers_must_be_finite(cls, value: Optional[float]) -> Optional[float]:
        if value is not None and not math.isfinite(value):
            raise ValueError("numeric values must be finite")
        return value


class TradeDraftPayload(_Strict):
    """`PUT /v1/trades/draft` body — a POSITIVE allowlist over draft-able fields.

    Every field is optional because a draft is, by definition, incomplete —
    the trader may have filled in only the asset and a note so far. What is
    NOT optional is the allowlist discipline: `extra="forbid"` refuses
    anything this contract does not name, exactly like `TradeCreate`.

    The field set mirrors `TradeCreate` deliberately rather than being
    hand-maintained separately: `DRAFT_TRADE_FIELDS` below is checked by a
    test to be a subset of `CREATABLE_TRADE_FIELDS` and disjoint from
    `SERVER_OWNED_ON_CREATE`, so a derived field (`session`, `killzone`,
    `strategy_used`, `asset_class`, or anything else the create endpoint
    itself derives) has no way into a draft — and no way to drift into one
    later without the contract test catching it.
    """

    trade_date: Optional[str] = None
    asset: Optional[str] = None
    entry_time: Optional[str] = None
    direction: Optional[str] = None
    bias: Optional[str] = None
    setup_type: Optional[str] = None
    timeframe: Optional[str] = None
    htf_bias: Optional[str] = None
    confirmation_model: Optional[str] = None
    entry_type: Optional[str] = None

    entry_price: Optional[float] = None
    stop_price: Optional[float] = None
    tp_price: Optional[float] = None
    exit_price: Optional[float] = None
    position_size: Optional[float] = None
    risk_amount: Optional[float] = None
    reward_amount: Optional[float] = None
    rr_realized: Optional[float] = None

    result: Optional[TradeResult] = None
    pnl: Optional[float] = None

    liquidity_sweep: Optional[Literal[0, 1]] = None
    fvg_used: Optional[Literal[0, 1]] = None
    order_block_used: Optional[Literal[0, 1]] = None
    bos: Optional[Literal[0, 1]] = None
    choch: Optional[Literal[0, 1]] = None
    followed_rules: Optional[Literal[0, 1]] = None
    mistake_tags: Optional[str] = None

    emotions_before: Optional[str] = None
    emotions_during: Optional[str] = None
    emotions_after: Optional[str] = None
    notes: Optional[str] = None
    trade_process_notes: Optional[str] = None

    # Autofill output, beside the draft rather than in it. Keys are checked
    # against the autofill allowlist below, so this is a second, wire-level
    # copy of the same filter the service already applied: a suggestion for a
    # derived field cannot round-trip even if something upstream let it be
    # stored.
    ai_suggestions: Optional[Dict[str, AutofillSuggestion]] = None

    @field_validator("ai_suggestions")
    @classmethod
    def _suggestions_must_be_suggestable(cls, value):
        if value is None:
            return value
        unknown = set(value) - _suggestable_fields()
        if unknown:
            raise ValueError("unsuggestable field")
        return value

    @field_validator(
        "pnl",
        "rr_realized",
        "risk_amount",
        "reward_amount",
        "entry_price",
        "stop_price",
        "tp_price",
        "exit_price",
        "position_size",
    )
    @classmethod
    def _numbers_must_be_finite(cls, value: Optional[float]) -> Optional[float]:
        if value is not None and not math.isfinite(value):
            raise ValueError("numeric values must be finite")
        return value


class TradeDraftResponse(_Strict):
    """`GET /v1/trades/draft` body. `draft` is `None` when the owner has none."""

    draft: Optional[TradeDraftPayload]


# The draft write surface, derived from the model itself so it cannot drift
# from `TradeDraftPayload`. `entry_time` is excluded from the comparison set
# for the same reason `CREATABLE_TRADE_FIELDS` excludes it below: it is not a
# `Trade` column, so "subset of the create allowlist" is about `Trade`
# columns, not wire fields. A contract test pins this as a subset of
# `CREATABLE_TRADE_FIELDS` and disjoint from `SERVER_OWNED_ON_CREATE` — see
# `TradeDraftPayload`'s docstring.
DRAFT_TRADE_FIELDS = frozenset(TradeDraftPayload.model_fields) - {
    "entry_time",
    # Not a `Trade` column and never becomes one: it is the provenance
    # sidecar the trader reviews, not a value the create path can accept.
    "ai_suggestions",
}


class TradeCreateResponse(TradeDetail):
    """`TradeDetail` plus whether this submit matched an existing trade.

    `duplicate_of` is the id of the trade this response actually describes
    when a fingerprint match was found — the same row `id` already carries,
    named separately so the client can distinguish "just created" from "this
    already existed" without a second lookup.
    """

    duplicate_of: Optional[int] = None


# The create write surface, derived from the model itself so it cannot drift
# from `TradeCreate`. Mirrors `EDITABLE_TRADE_FIELDS` below.
CREATABLE_TRADE_FIELDS = frozenset(TradeCreate.model_fields) - {"entry_time"}

# Every `Trade` column NOT reachable through `POST /v1/trades`, named
# explicitly for the same reason `SERVER_OWNED_TRADE_COLUMNS` is: a column
# added to the model belongs to neither set until someone files it here, and
# the contract test fails until they do.
SERVER_OWNED_ON_CREATE = frozenset(
    {
        "id",
        "user_id",
        "trade_hash",
        "create_idempotency_key",
        "is_sample",
        "created_at",
        "updated_at",
        "strategy_id",
        "strategy_used",
        "day_of_week",
        "session",
        "killzone",
        "asset_class",
        "rr_planned",
        "ai_grade",
        "user_grade",
    }
)


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
        "create_idempotency_key",
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


# ------------------------------------------------------- screenshot lifecycle

# The upload types the presigned policy will bind. Pinned against
# `storage.ALLOWED_CONTENT_TYPES` by a test rather than derived, because a
# `Literal` needs literal members — the test is what keeps the two together.
ScreenshotContentType = Literal["image/png", "image/jpeg", "image/webp"]


class ScreenshotPresignRequest(_Strict):
    """What the browser is asking permission to upload.

    Only the content type. The object key is chosen by the server and is never
    influenced by the client — a user-supplied key component is a
    path-traversal and overwrite primitive.
    """

    content_type: ScreenshotContentType


class ScreenshotPresignResponse(_Strict):
    """A short-lived PUT URL into a namespace with no download path.

    `max_bytes` is advisory: a presigned PUT cannot bind a maximum size, so
    the real gate runs server-side at finalize. Sending it lets the browser
    spare a trader a slow upload that would be refused anyway.
    """

    url: str
    key: str
    expires_in: int
    max_bytes: int


class ScreenshotUrlRequest(_Strict):
    """A link to a chart image the server will fetch on the trader's behalf.

    Just the URL. It is untrusted in two separate ways and both are handled
    elsewhere: `url_ingest` decides whether the address may be connected to at
    all, and the bytes that come back are put through the same quarantine and
    `finalize_upload` re-encode as any browser upload. Nothing here influences
    where the object lands — the key is still server-chosen.
    """

    url: str


class ScreenshotKeyRequest(_Strict):
    """A key the browser received back from presign.

    It is a CLAIM, never a location. Every handler re-derives the caller's own
    expected prefix and refuses anything outside it, so a forged key cannot
    name another owner's object.
    """

    key: str
