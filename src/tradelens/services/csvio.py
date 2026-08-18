import io
import logging

import pandas as pd

from src.tradelens.services.ownership import require_user_id
from src.tradelens.services.trade_service import (
    compute_trade_hash,
    create_trade,
    trade_hash_exists,
)

# CSV columns match Trade model column names exactly (snake_case).
# Import round-trips through create_trade(), which filters by model column keys.
CSV_COLUMNS = [
    "trade_date",
    "asset",
    "asset_class",
    "session",
    "timeframe",
    "direction",
    "bias",
    "setup_type",
    "entry_price",
    "stop_price",
    "tp_price",
    "exit_price",
    "position_size",
    "risk_amount",
    "result",
    "pnl",
    "rr_planned",
    "rr_realized",
    "strategy_used",
    "emotions_before",
    "emotions_during",
    "emotions_after",
    "notes",
]

_REQUIRED_IMPORT_COLS = {"trade_date", "asset", "direction", "result", "pnl"}

_log = logging.getLogger(__name__)

# Import errors are rendered straight into the UI, so they are written here
# rather than taken from the exception. A driver or parser message can carry
# a database URL, a SQL statement or a fragment of the row; the row number
# is the part the user actually needs to act on, and it is safe.
_PARSE_FAILED = (
    "Could not read that file as a CSV. Export a file first to see the expected format."
)
_ROW_FAILED = (
    "Row {row}: could not be imported. Check its values against an exported file."
)


def export_trades_csv(df: pd.DataFrame) -> bytes:
    """
    Return CSV bytes from a trades DataFrame, column-ordered per CSV_COLUMNS.
    Columns present in CSV_COLUMNS but absent in df are exported as empty.
    Suitable for passing directly to st.download_button(data=...).
    """
    out = df.reindex(columns=CSV_COLUMNS)
    return out.to_csv(index=False).encode("utf-8")


def import_trades_csv(file, user_id: int) -> tuple[int, int, list[str]]:
    """
    Parse a CSV UploadedFile and insert each row as a Trade via create_trade().

    The owner is required. It was `Optional[int]` defaulting to None, which
    matched only legacy NULL-owner rows for the duplicate check rather than
    raising — a missing owner looked like an empty account instead of a
    programming error.

    Returns (rows_inserted, skipped_duplicates, errors). Duplicate rows — those
    whose trade_hash already exists (scoped to `user_id`) or repeat within the
    file — are skipped, not inserted. Never raises on a bad row; bad rows go
    into `errors`. An invalid owner still raises — that is a caller defect,
    not a row the trader can fix.
    """
    owner = require_user_id(user_id)
    try:
        df = pd.read_csv(io.BytesIO(file.read()))
    except Exception:
        _log.exception("CSV import failed to parse the uploaded file")
        return 0, 0, [_PARSE_FAILED]

    missing = _REQUIRED_IMPORT_COLS - set(df.columns)
    if missing:
        return 0, 0, [f"CSV is missing required columns: {', '.join(sorted(missing))}"]

    rows_inserted = 0
    skipped = 0
    errors: list[str] = []
    seen_hashes: set[str] = set()

    for i, row in df.iterrows():
        try:
            # Drop NaN cells so optional fields aren't passed as float('nan')
            trade_data = {k: v for k, v in row.items() if pd.notna(v)}
            trade_data["user_id"] = owner

            row_hash = compute_trade_hash(trade_data)
            if row_hash in seen_hashes or trade_hash_exists(row_hash, user_id=owner):
                skipped += 1
                continue
            seen_hashes.add(row_hash)

            create_trade(trade_data)
            rows_inserted += 1
        except Exception:
            # +2: 1-based + header row. The number is the actionable part;
            # the exception itself goes to the log, never to the page.
            _log.exception("CSV import failed on row %s", i + 2)
            errors.append(_ROW_FAILED.format(row=i + 2))

    return rows_inserted, skipped, errors
