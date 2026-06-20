"""Read/write access to the performance_metrics table. No Streamlit imports."""

from typing import Optional

from src.tradelens.db.models import PerformanceMetrics
from src.tradelens.db.session import SessionLocal


def get_computed_at(user_id: int = 1) -> Optional[str]:
    """Return the ISO computed_at timestamp for the last recompute, or None.

    Returns None if no row exists for this user or if the table is inaccessible.
    Never raises — callers can treat None as "not yet computed".
    """
    db = SessionLocal()
    try:
        row = (
            db.query(PerformanceMetrics)
            .filter(PerformanceMetrics.user_id == user_id)
            .first()
        )
        return row.computed_at if row else None
    except Exception:
        return None
    finally:
        db.close()
