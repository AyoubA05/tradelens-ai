"""Read/write access to the performance_metrics table. No Streamlit imports."""

from typing import Optional

from src.tradelens.db.models import PerformanceMetrics
from src.tradelens.db.session import SessionLocal
from src.tradelens.services.ownership import require_user_id


def get_computed_at(user_id: int) -> Optional[str]:
    """Return the ISO computed_at timestamp for the last recompute, or None.

    Returns None if no row exists for this user or if the table is inaccessible.
    Never raises — callers can treat None as "not yet computed".
    """
    owner = require_user_id(user_id)
    db = SessionLocal()
    try:
        row = (
            db.query(PerformanceMetrics)
            .filter(PerformanceMetrics.user_id == owner)
            .first()
        )
        return row.computed_at if row else None
    except Exception:
        return None
    finally:
        db.close()
