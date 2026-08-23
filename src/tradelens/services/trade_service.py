# Keep trade records structured and consistent so future analysis can filter by fields like session, strategy, emotion, RR, and P&L instead of parsing notes.

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import func, update
from sqlalchemy.orm import Session, selectinload

from src.tradelens.db.models import AIAnalysis, Correction, Screenshot, Trade
from src.tradelens.db.session import SessionLocal
from src.tradelens.services.ownership import require_user_id
from src.tradelens.services.trade_validation import canonical_outcome, is_blank


def _calc_rr(
    entry: float, stop: float, target: float, direction: str
) -> Optional[float]:
    """Risk-to-reward ratio for Long or Short."""
    try:
        risk = abs(entry - stop)
        if risk == 0:
            return None
        reward = abs(target - entry)
        return round(reward / risk, 2)
    except (TypeError, ZeroDivisionError):
        return None


def _norm_num(value) -> str:
    """Normalize a numeric field for hashing (stable across int/float/None)."""
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return ""


def compute_trade_hash(trade_data: dict) -> str:
    """Deterministic fingerprint of a trade's identifying fields.

    Used to catch double-submits, Streamlit reruns, and CSV re-imports. entry_time
    is included when present (the New Trade form passes it) and simply omitted for
    CSV rows that lack one.
    """
    parts = [
        str(trade_data.get("trade_date") or "").strip()[:10],
        str(trade_data.get("asset") or "").strip().upper(),
        str(trade_data.get("direction") or "").strip().lower(),
        str(trade_data.get("entry_time") or "").strip(),
        _norm_num(trade_data.get("entry_price")),
        _norm_num(trade_data.get("stop_price")),
        _norm_num(trade_data.get("exit_price")),
        _norm_num(trade_data.get("pnl")),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def trade_hash_exists(trade_hash: str, user_id: int) -> bool:
    """True if this user already has a trade with this hash.

    `user_id` is required. It used to default to None, which skipped the owner
    filter entirely — so a hash collision with a completely different trader
    reported "you already logged this".
    """
    owner = require_user_id(user_id)
    db: Session = SessionLocal()
    try:
        query = db.query(Trade).filter(
            Trade.trade_hash == trade_hash, Trade.user_id == owner
        )
        return db.query(query.exists()).scalar()
    finally:
        db.close()


def find_recent_duplicate(
    trade_data: dict, user_id: int, within_seconds: int = 60
) -> Optional[Trade]:
    """Return this user's same-hash trade created within `within_seconds`, or None.

    Powers the "is this a duplicate?" prompt that catches double-clicks. The
    owner is required: this returns a Trade object that the UI shows to the
    caller, so an unscoped match handed one trader another trader's record.
    """
    owner = require_user_id(user_id)
    trade_hash = compute_trade_hash(trade_data)
    cutoff = (
        datetime.now(timezone.utc) - timedelta(seconds=within_seconds)
    ).isoformat()
    db: Session = SessionLocal()
    try:
        return (
            db.query(Trade)
            .filter(
                Trade.trade_hash == trade_hash,
                Trade.created_at >= cutoff,
                Trade.user_id == owner,
            )
            .order_by(Trade.created_at.desc())
            .first()
        )
    finally:
        db.close()


def create_trade(trade_data: dict, *, user_id: int) -> Trade:
    """
    Insert a trade row. Auto-calculates day_of_week, rr_planned, rr_realized,
    and a trade_hash fingerprint. Returns the persisted Trade.
    """
    owner = require_user_id(user_id)
    data = dict(trade_data)
    # Authentication context owns this field. A body may contain a stale or
    # malicious user_id, but it can never select where the row is written.
    data["user_id"] = owner

    # A stored row may never contradict itself: P&L decides the outcome label.
    data["result"] = canonical_outcome(data.get("result"), data.get("pnl"))

    # Fingerprint BEFORE dropping non-model keys (entry_time is hash-only).
    data["trade_hash"] = compute_trade_hash(data)

    # Auto-calculate day_of_week from trade_date
    trade_date_str = data.get("trade_date")
    if trade_date_str and not data.get("day_of_week"):
        try:
            dt = datetime.strptime(str(trade_date_str), "%Y-%m-%d")
            data["day_of_week"] = dt.strftime("%A")
        except ValueError:
            pass

    direction = data.get("direction", "Long")
    entry = data.get("entry_price")
    stop = data.get("stop_price")
    tp = data.get("tp_price")
    exit_price = data.get("exit_price")

    # Auto-calculate rr_planned
    if entry and stop and tp:
        data["rr_planned"] = _calc_rr(entry, stop, tp, direction)

    # Auto-calculate rr_realized
    if entry and stop and exit_price:
        data["rr_realized"] = _calc_rr(entry, stop, exit_price, direction)

    now = datetime.now(timezone.utc).isoformat()
    data.setdefault("created_at", now)
    data.setdefault("updated_at", now)

    # Strip keys not in the model
    valid_cols = {c.key for c in Trade.__table__.columns}
    filtered = {k: v for k, v in data.items() if k in valid_cols}

    db: Session = SessionLocal()
    try:
        trade = Trade(**filtered)
        db.add(trade)
        db.commit()
        db.refresh(trade)
        return trade
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_trades(
    *,
    user_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    asset: Optional[str] = None,
    result: Optional[str] = None,
    session: Optional[str] = None,
    strategy: Optional[str] = None,
) -> list[Trade]:
    """Return one user's trades, filtered by the optional parameters.

    Ordered by trade_date DESC. A None filter argument means "do not filter on
    it"; `user_id` is not one of those and has no default.

    **Keyword-only, deliberately.** `start_date` used to sit first, so a
    positional `get_trades(uid)` silently asked for "trades on or after <a user
    id>". That happened once already while writing the Step 11 isolation
    harness. Every argument must be named.

    **The owner is required, deliberately.** It previously defaulted to an
    `_UNSCOPED` sentinel that applied no user filter at all, so the safe call
    and the every-tenant call differed by one easily-omitted keyword.
    """
    owner = require_user_id(user_id)
    db: Session = SessionLocal()
    try:
        query = db.query(Trade).options(selectinload(Trade.screenshots))
        query = query.filter(Trade.user_id == owner)

        if start_date:
            query = query.filter(Trade.trade_date >= start_date)
        if end_date:
            query = query.filter(Trade.trade_date <= end_date)
        if asset:
            query = query.filter(Trade.asset.ilike(f"%{asset}%"))
        if result and result != "All":
            query = query.filter(Trade.result == result)
        if session and session != "All":
            query = query.filter(Trade.session == session)
        if strategy:
            query = query.filter(Trade.strategy_used.ilike(f"%{strategy}%"))

        return query.order_by(Trade.trade_date.desc()).all()
    finally:
        db.close()


@dataclass
class TradePage:
    trades: List[Trade]
    total: int
    limit: int
    offset: int


def list_trades(
    *,
    user_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    asset: Optional[str] = None,
    session: Optional[str] = None,
    setup_type: Optional[str] = None,
    result: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> TradePage:
    """A paginated, filtered view of one user's trades, with a total count.

    New rather than a `get_trades` extension: `get_trades` has no pagination,
    ends its query in `.all()`, and existing callers depend on that contract
    unchanged.

    `limit` and `offset` are clamped server-side rather than trusted — a
    caller must not be able to request the whole table by passing an
    unbounded `limit`.

    The count query and the page query are built from one shared filtered
    query object (`_filtered`) rather than two independent constructions. Two
    separate filter-building code paths are how a total and a page silently
    drift apart — the total would count one thing while the page shows
    another, which reads to a trader as a phantom page.

    Ordered `trade_date desc, id desc`. `trade_date` alone is a partial order:
    trades sharing a date can be returned in either relative order from one
    call to the next, so a same-day row can appear on two pages, or on
    neither, as offsets shift. `id` is a total tiebreaker, so the order —
    and therefore the pagination — is stable.
    """
    owner = require_user_id(user_id)
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))

    db: Session = SessionLocal()
    try:

        def _filtered(query):
            query = query.filter(Trade.user_id == owner)
            if start_date:
                query = query.filter(Trade.trade_date >= start_date)
            if end_date:
                query = query.filter(Trade.trade_date <= end_date)
            if asset:
                # Exact, like every other filter here — NOT `ilike('%..%')`.
                # A substring match makes `asset=NQ` also return MNQ, in both
                # the rows AND the total, and `asset=%` match the whole
                # journal. The filter is parameterised either way, so this is
                # not injection; it is a control that does not narrow the way
                # its name says it does, which puts wrong numbers in front of
                # a trader reviewing one instrument.
                #
                # `get_trades` keeps its substring behaviour deliberately:
                # that is the Streamlit search box, where "type a fragment"
                # is the contract callers already rely on.
                query = query.filter(Trade.asset == asset)
            if session:
                query = query.filter(Trade.session == session)
            if setup_type:
                query = query.filter(Trade.setup_type == setup_type)
            if result:
                query = query.filter(Trade.result == result)
            return query

        total = _filtered(db.query(func.count(Trade.id))).scalar() or 0

        trades = (
            _filtered(db.query(Trade).options(selectinload(Trade.screenshots)))
            .order_by(Trade.trade_date.desc(), Trade.id.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

        return TradePage(trades=trades, total=total, limit=limit, offset=offset)
    finally:
        db.close()


def get_trade(trade_id: int, user_id: int) -> Optional[Trade]:
    """Return this user's trade (relationships eager-loaded), or None.

    The owner is required. It was `Optional[int]`, and while a None failed
    closed — matching only legacy NULL-owner rows — that made a missing owner
    look like a missing trade instead of a programming error.

    Root cause of the Journal-page error (Item 11): this returned the Trade
    with only `screenshots` eager-loaded and then closed the session — so any
    consumer touching `trade.ai_analysis` afterwards raised
    DetachedInstanceError ("lazy load operation of attribute 'ai_analysis'
    cannot proceed"). Every relationship the detail panel can reach is now
    loaded before the session closes.
    """
    owner = require_user_id(user_id)
    db: Session = SessionLocal()
    try:
        return (
            db.query(Trade)
            .options(selectinload(Trade.screenshots), selectinload(Trade.ai_analysis))
            .filter(Trade.id == trade_id, Trade.user_id == owner)
            .first()
        )
    finally:
        db.close()


def update_trade(trade_id: int, user_id: int, **fields) -> Optional[Trade]:
    """Update editable fields on this user's trade, or return None.

    The owner is required, for the same reason as `get_trade`. Ownership and
    primary keys are never editable through this API.
    """
    owner = require_user_id(user_id)
    valid_cols = {c.key for c in Trade.__table__.columns} - {"id", "user_id"}
    updates = {k: v for k, v in fields.items() if k in valid_cols}
    db: Session = SessionLocal()
    try:
        trade = (
            db.query(Trade).filter(Trade.id == trade_id, Trade.user_id == owner).first()
        )
        if trade is None:
            return None
        # Editing either half of the outcome pair re-validates the whole pair,
        # so a partial edit can't leave the row contradicting itself.
        #
        # A new P&L is canonical: it re-derives the label rather than being
        # vetoed by the label that described the old value. A label edit alone
        # is still checked against the P&L already stored.
        if "pnl" in updates:
            stale_label = trade.result if is_blank(updates["pnl"]) else None
            updates["result"] = canonical_outcome(
                updates.get("result", stale_label), updates["pnl"]
            )
        elif "result" in updates:
            updates["result"] = canonical_outcome(updates["result"], trade.pnl)
        for key, value in updates.items():
            setattr(trade, key, value)
        trade.updated_at = datetime.now(timezone.utc).isoformat()
        db.commit()
        db.refresh(trade)
        return trade
    finally:
        db.close()


def delete_trade(trade_id: int, user_id: int) -> bool:
    """Delete this user's trade and return whether a row was removed.

    The owner is required, for the same reason as `get_trade`.
    """
    owner = require_user_id(user_id)
    db: Session = SessionLocal()
    try:
        trade = (
            db.query(Trade).filter(Trade.id == trade_id, Trade.user_id == owner).first()
        )
        if trade is None:
            return False
        db.delete(trade)
        db.commit()
        return True
    finally:
        db.close()


def delete_all_trades(user_id: int) -> int:
    """Delete every trade owned by one concrete user and return the row count."""
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("user_id must be a positive integer")

    db: Session = SessionLocal()
    try:
        trade_ids = [
            trade_id
            for (trade_id,) in db.query(Trade.id).filter(Trade.user_id == user_id).all()
        ]
        if not trade_ids:
            return 0

        db.query(Correction).filter(Correction.trade_id.in_(trade_ids)).delete(
            synchronize_session=False
        )
        db.query(AIAnalysis).filter(AIAnalysis.trade_id.in_(trade_ids)).delete(
            synchronize_session=False
        )
        db.query(Screenshot).filter(Screenshot.trade_id.in_(trade_ids)).delete(
            synchronize_session=False
        )
        deleted = (
            db.query(Trade)
            .filter(Trade.user_id == user_id, Trade.id.in_(trade_ids))
            .delete(synchronize_session=False)
        )
        db.commit()
        return deleted
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_primary_screenshot(trade_id: int, *, user_id: int) -> Optional[str]:
    """Return the file_path of a trade's first screenshot, or None.

    Best-effort lookup for the Trade-of-the-Week thumbnail; never raises on a
    missing trade or missing screenshot — the caller renders without a thumbnail.
    """
    owner = require_user_id(user_id)
    db: Session = SessionLocal()
    try:
        from src.tradelens.db.models import Screenshot

        shot = (
            db.query(Screenshot)
            .join(Trade, Trade.id == Screenshot.trade_id)
            .filter(Screenshot.trade_id == trade_id, Trade.user_id == owner)
            .order_by(Screenshot.id.asc())
            .first()
        )
        return shot.file_path if shot else None
    finally:
        db.close()


@dataclass
class TradeUpdateOutcome:
    """The result of an optimistic-concurrency edit.

    `status` is one of "updated", "not_found" or "conflict". `trade` is set
    only for "updated"; `current_updated_at` only for "conflict", so the
    caller can tell a trader what the row looks like now.
    """

    status: str
    trade: Optional[Trade] = None
    current_updated_at: Optional[str] = None


def update_trade_if_unchanged(
    trade_id: int,
    user_id: int,
    expected_updated_at: str,
    updates: dict,
) -> TradeUpdateOutcome:
    """Edit one trade, but only while it still looks the way the client saw it.

    **The guard is a single conditional UPDATE, never a check-then-update.**
    The predicate carries all three of the trade id, the authenticated owner
    and `expected_updated_at`, and the decision is the rowcount. Reading the
    row, comparing `updated_at` in Python and then writing would leave a
    window in which another request commits in between — which is precisely
    the lost update this parameter exists to prevent, reintroduced by the
    guard itself. That is the same TOCTOU Phase 0 had to remove from
    `restore_website_session_handle`, and it is not coming back here.

    The SELECT above the write is for OUTCOME DERIVATION only, never for the
    concurrency decision: re-deriving `result` needs whichever half of the
    outcome pair the caller did not send. It is safe precisely because the
    UPDATE below refuses to land if the row moved after that read.

    A rowcount of 0 means either the trade is not the caller's or the row
    moved on, so it is re-read once, owner-scoped, to tell a 404 from a 409.

    Unlike `update_trade`, unknown keys are rejected rather than filtered:
    a caller passing a field this function silently drops has a bug, and at
    an HTTP edge a silently dropped field is an edit a trader believes they
    made.
    """
    owner = require_user_id(user_id)
    editable = {c.key for c in Trade.__table__.columns} - {"id", "user_id"}
    unknown = set(updates) - editable
    if unknown:
        raise ValueError(f"not editable: {sorted(unknown)}")

    values = dict(updates)
    db: Session = SessionLocal()
    try:
        # A tuple query, not an entity query: nothing enters the identity map,
        # so the Core UPDATE below cannot be shadowed by a stale ORM object.
        current = (
            db.query(Trade.result, Trade.pnl)
            .filter(Trade.id == trade_id, Trade.user_id == owner)
            .first()
        )
        if current is None:
            return TradeUpdateOutcome(status="not_found")

        # Editing either half of the outcome pair re-validates the whole pair,
        # so a partial edit can't leave the row contradicting itself. A new
        # P&L is canonical; a label edit alone is checked against the stored
        # P&L. Mirrors `update_trade` deliberately — one rule, two callers.
        if "pnl" in values:
            stale_label = current.result if is_blank(values["pnl"]) else None
            values["result"] = canonical_outcome(
                values.get("result", stale_label), values["pnl"]
            )
        elif "result" in values:
            values["result"] = canonical_outcome(values["result"], current.pnl)

        values["updated_at"] = datetime.now(timezone.utc).isoformat()

        written = db.execute(
            update(Trade)
            .where(
                Trade.id == trade_id,
                Trade.user_id == owner,
                Trade.updated_at == expected_updated_at,
            )
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        if written.rowcount != 1:
            db.rollback()
            row = (
                db.query(Trade.updated_at)
                .filter(Trade.id == trade_id, Trade.user_id == owner)
                .first()
            )
            if row is None:
                return TradeUpdateOutcome(status="not_found")
            return TradeUpdateOutcome(status="conflict", current_updated_at=row[0])
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    return TradeUpdateOutcome(status="updated", trade=get_trade(trade_id, owner))
