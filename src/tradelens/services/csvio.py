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

# Decision S4: an import is synchronous and bounded. A file with more data rows
# than this is refused whole, before anything is inserted.
MAX_IMPORT_ROWS = 5000
MAX_IMPORT_BYTES = 1_048_576

# Decision S5: a spreadsheet treats a cell starting with one of these as a
# formula. A trader's own note must never execute when their export is opened.
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

# Numeric columns are exempt: a leading "-" there is a negative number.
NUMERIC_COLUMNS = frozenset(
    {
        "entry_price",
        "stop_price",
        "tp_price",
        "exit_price",
        "position_size",
        "risk_amount",
        "pnl",
        "rr_planned",
        "rr_realized",
    }
)
TEXT_COLUMNS = frozenset(c for c in CSV_COLUMNS if c not in NUMERIC_COLUMNS)


class TooManyRows(ValueError):
    """The file exceeds MAX_IMPORT_ROWS; nothing was imported."""


class ImportTooLarge(ValueError):
    """The raw CSV exceeds the shared one-megabyte service boundary."""


def neutralise_formula(value):
    """Prefix a formula-leading string with `'` so a spreadsheet shows it as text."""
    # Escape formula-looking text and every literal apostrophe run before it.
    # Import removes exactly this one added quote, preserving the original run.
    if isinstance(value, str) and value.lstrip("'").startswith(FORMULA_PREFIXES):
        return "'" + value
    return value


def restore_formula(value):
    """Undo `neutralise_formula`, so an export imports back losslessly.

    Only a `'` followed by a formula prefix is removed; ordinary text that
    happens to start with a quote is left exactly as it was.
    """
    if (
        isinstance(value, str)
        and len(value) > 1
        and value[0] == "'"
        and value[1:].lstrip("'").startswith(FORMULA_PREFIXES)
    ):
        return value[1:]
    return value


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
    for column in TEXT_COLUMNS:
        out[column] = out[column].map(neutralise_formula)
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
    raw = file.read(MAX_IMPORT_BYTES + 1)
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    if len(raw) > MAX_IMPORT_BYTES:
        raise ImportTooLarge()
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception:
        # Parser exceptions can embed uploaded cells. Keep private trade data
        # out of application logs; the fixed response is sufficient here.
        _log.warning("CSV import failed to parse the uploaded file")
        return 0, 0, [_PARSE_FAILED]

    if len(df.index) > MAX_IMPORT_ROWS:
        raise TooManyRows()

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
            trade_data = {
                k: (restore_formula(v) if k in TEXT_COLUMNS else v)
                for k, v in row.items()
                if k in CSV_COLUMNS and pd.notna(v)
            }
            trade_data["user_id"] = owner

            row_hash = compute_trade_hash(trade_data)
            if row_hash in seen_hashes or trade_hash_exists(row_hash, user_id=owner):
                skipped += 1
                continue
            seen_hashes.add(row_hash)

            create_trade(trade_data, user_id=owner)
            rows_inserted += 1
        except Exception:
            # +2: 1-based + header row. The number is the actionable part;
            # the exception itself goes to the log, never to the page.
            # SQLAlchemy and validation exceptions can include all parameters,
            # including notes. Record only the safe row number.
            _log.warning("CSV import failed on row %s", i + 2)
            errors.append(_ROW_FAILED.format(row=i + 2))

    return rows_inserted, skipped, errors


def import_trades_csv_text(csv_text: str, user_id: int) -> tuple[int, int, list[str]]:
    """`import_trades_csv` for text received over the API, row-capped first.

    Raises `TooManyRows` before a single row is inserted when the file has
    more than `MAX_IMPORT_ROWS` data rows (read at call time). A file that
    does not parse is reported the same way `import_trades_csv` reports it.
    """
    owner = require_user_id(user_id)
    return import_trades_csv(io.BytesIO(csv_text.encode("utf-8")), owner)
