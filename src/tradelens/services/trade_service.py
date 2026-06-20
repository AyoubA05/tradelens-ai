# Keep trade records structured and consistent so future analysis can filter by fields like session, strategy, emotion, RR, and P&L instead of parsing notes.

from datetime import datetime, timezone
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


def create_trade(trade_data: dict) -> Trade:
    """
    Insert a trade row. Auto-calculates day_of_week, rr_planned, rr_realized.
    Returns the persisted Trade.
    """
    data = dict(trade_data)

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
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    asset: Optional[str] = None,
    result: Optional[str] = None,
    session: Optional[str] = None,
    strategy: Optional[str] = None,
) -> list[Trade]:
    """
    Return trades filtered by optional parameters.
    If a parameter is None, do not filter on it.
    Order by trade_date DESC.
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

        return query.order_by(Trade.trade_date.desc()).all()
    finally:
        db.close()
