import io

import pandas as pd

from src.tradelens.services.trade_service import create_trade

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


def export_trades_csv(df: pd.DataFrame) -> bytes:
    """
    Return CSV bytes from a trades DataFrame, column-ordered per CSV_COLUMNS.
    Columns present in CSV_COLUMNS but absent in df are exported as empty.
    Suitable for passing directly to st.download_button(data=...).
    """
    out = df.reindex(columns=CSV_COLUMNS)
    return out.to_csv(index=False).encode("utf-8")


def import_trades_csv(file) -> tuple[int, list[str]]:
    """
    Parse a CSV UploadedFile and insert each row as a Trade via create_trade().

    Returns (rows_inserted, errors). Never raises — bad rows are collected in errors.
    """
    try:
        df = pd.read_csv(io.BytesIO(file.read()))
    except Exception as exc:
        return 0, [f"Could not parse CSV: {exc}"]

    missing = _REQUIRED_IMPORT_COLS - set(df.columns)
    if missing:
        return 0, [f"CSV is missing required columns: {', '.join(sorted(missing))}"]

    rows_inserted = 0
    errors: list[str] = []

    for i, row in df.iterrows():
        try:
            # Drop NaN cells so optional fields aren't passed as float('nan')
            trade_data = {k: v for k, v in row.items() if pd.notna(v)}
            create_trade(trade_data)
            rows_inserted += 1
        except Exception as exc:
            errors.append(f"Row {i + 2}: {exc}")  # +2: 1-based + header row

    return rows_inserted, errors
