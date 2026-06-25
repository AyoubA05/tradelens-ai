# Keep trade records structured and consistent so future analysis can filter by fields like session, strategy, emotion, RR, and P&L instead of parsing notes.

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session, selectinload

from src.tradelens.db.models import Trade
from src.tradelens.db.session import SessionLocal


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


def trade_hash_exists(trade_hash: str, user_id=None) -> bool:
    """True if a trade with this hash already exists (optionally scoped to a user)."""
    db: Session = SessionLocal()
    try:
        query = db.query(Trade).filter(Trade.trade_hash == trade_hash)
        if user_id is not None:
            query = query.filter(Trade.user_id == user_id)
        return db.query(query.exists()).scalar()
    finally:
        db.close()


def find_recent_duplicate(
    trade_data: dict, user_id=None, within_seconds: int = 60
) -> Optional[Trade]:
    """Return a same-hash trade created within the last `within_seconds`, or None.

    Scopes to `user_id` when provided. Powers the "is this a duplicate?" prompt
    that catches double-clicks and reruns.
    """
    trade_hash = compute_trade_hash(trade_data)
    cutoff = (
        datetime.now(timezone.utc) - timedelta(seconds=within_seconds)
    ).isoformat()
    db: Session = SessionLocal()
    try:
        query = db.query(Trade).filter(
            Trade.trade_hash == trade_hash, Trade.created_at >= cutoff
        )
        if user_id is not None:
            query = query.filter(Trade.user_id == user_id)
        return query.order_by(Trade.created_at.desc()).first()
    finally:
        db.close()


def create_trade(trade_data: dict) -> Trade:
    """
    Insert a trade row. Auto-calculates day_of_week, rr_planned, rr_realized,
    and a trade_hash fingerprint. Returns the persisted Trade.
    """
    data = dict(trade_data)

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


# Sentinel: distinguishes "no user filter at all" (default, legacy/all trades)
# from an explicit user_id of None (the legacy single user → only NULL-owner rows).
_UNSCOPED = object()


def get_trades(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    asset: Optional[str] = None,
    result: Optional[str] = None,
    session: Optional[str] = None,
    strategy: Optional[str] = None,
    user_id=_UNSCOPED,
) -> list[Trade]:
    """
    Return trades filtered by optional parameters.
    If a parameter is None, do not filter on it.
    Order by trade_date DESC.

    user_id scoping (Session B): when provided, returns trades owned by that user
    OR legacy trades with a NULL owner (so existing data stays visible). Passing
    None scopes to NULL-owner trades only (the secrets-fallback legacy user).
    Omitting the argument applies no user filter (all trades).
    """
    db: Session = SessionLocal()
    try:
        query = db.query(Trade).options(selectinload(Trade.screenshots))

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
        if user_id is not _UNSCOPED:
            if user_id is None:
                query = query.filter(Trade.user_id.is_(None))
            else:
                query = query.filter(
                    (Trade.user_id == user_id) | (Trade.user_id.is_(None))
                )

        return query.order_by(Trade.trade_date.desc()).all()
    finally:
        db.close()


def get_trade(trade_id: int) -> Optional[Trade]:
    """Return a single trade (with screenshots eager-loaded), or None."""
    db: Session = SessionLocal()
    try:
        return (
            db.query(Trade)
            .options(selectinload(Trade.screenshots))
            .filter(Trade.id == trade_id)
            .first()
        )
    finally:
        db.close()


def update_trade(trade_id: int, **fields) -> Optional[Trade]:
    """Update editable fields on a trade. Unknown keys are ignored. Returns the
    refreshed Trade, or None if it does not exist."""
    valid_cols = {c.key for c in Trade.__table__.columns} - {"id"}
    updates = {k: v for k, v in fields.items() if k in valid_cols}
    db: Session = SessionLocal()
    try:
        trade = db.query(Trade).filter(Trade.id == trade_id).first()
        if trade is None:
            return None
        for key, value in updates.items():
            setattr(trade, key, value)
        trade.updated_at = datetime.now(timezone.utc).isoformat()
        db.commit()
        db.refresh(trade)
        return trade
    finally:
        db.close()


def delete_trade(trade_id: int) -> bool:
    """Delete a trade (and its screenshots/analysis via cascade). Returns True
    when a row was removed."""
    db: Session = SessionLocal()
    try:
        trade = db.query(Trade).filter(Trade.id == trade_id).first()
        if trade is None:
            return False
        db.delete(trade)
        db.commit()
        return True
    finally:
        db.close()


def get_primary_screenshot(trade_id: int) -> Optional[str]:
    """Return the file_path of a trade's first screenshot, or None.

    Best-effort lookup for the Trade-of-the-Week thumbnail; never raises on a
    missing trade or missing screenshot — the caller renders without a thumbnail.
    """
    if trade_id is None:
        return None
    db: Session = SessionLocal()
    try:
        from src.tradelens.db.models import Screenshot

        shot = (
            db.query(Screenshot)
            .filter(Screenshot.trade_id == trade_id)
            .order_by(Screenshot.id.asc())
            .first()
        )
        return shot.file_path if shot else None
    finally:
        db.close()
