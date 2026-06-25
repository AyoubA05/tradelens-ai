"""
Sample/demo trade management for the Settings page (Session A).

Loads a batch of clearly-flagged demo trades (is_sample = 1) and clears ONLY
those rows — real trades are never touched. Streamlit-free; safe to import from
pages and tests.
"""

from __future__ import annotations

import pandas as pd

from src.tradelens.db.models import Trade
from src.tradelens.db.session import SessionLocal

# Model column names, minus the autoincrement primary key.
_MODEL_COLS = {c.key for c in Trade.__table__.columns} - {"id"}


def count_sample_trades() -> int:
    """How many sample (is_sample = 1) trades currently exist."""
    db = SessionLocal()
    try:
        return db.query(Trade).filter(Trade.is_sample == 1).count()
    finally:
        db.close()


def clear_sample_trades() -> int:
    """Delete only sample-flagged trades. Returns the number removed."""
    db = SessionLocal()
    try:
        deleted = db.query(Trade).filter(Trade.is_sample == 1).delete()
        db.commit()
        return deleted
    finally:
        db.close()


def load_sample_trades() -> int:
    """Insert a deterministic batch of demo trades flagged is_sample = 1.

    Clears any existing sample rows first so repeated loads don't pile up
    duplicates. Reuses the same synthetic dataset the demo dashboard renders.
    Returns the number of rows inserted.
    """
    from src.tradelens.services.demo import get_demo_df

    clear_sample_trades()

    df = get_demo_df()
    rows = []
    for _, record in df.iterrows():
        data = {
            key: (None if pd.isna(value) else value)
            for key, value in record.items()
            if key in _MODEL_COLS
        }
        data["is_sample"] = 1
        data["notes"] = "Demo Data"
        rows.append(Trade(**data))

    db = SessionLocal()
    try:
        db.add_all(rows)
        db.commit()
        return len(rows)
    finally:
        db.close()
