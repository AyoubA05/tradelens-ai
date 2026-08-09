"""Pure presentation helpers for the Journal ledger.

No Streamlit import. `2_Trades.py` runs its whole script at module scope, so a
unit test that imports the page boots a page and needs a database — the same
reason Tasks 5-7 put the Overview's band logic in `overview_bands.py` rather
than in `app.py`. The row-styling rule is a real contract (spec 6.3: neutral
by row, semantic colour only on signed money), so it lives where a test can
reach it directly.
"""

from __future__ import annotations

from typing import Mapping

import pandas as pd

from src.tradelens.ui.design_system import TL_DANGER, TL_SUCCESS
from src.tradelens.utils.format import humanize

LEDGER_MARKS: Mapping[str, str] = {"Win": "▲", "Loss": "▼", "Breakeven": "■"}

# Money columns are the only ones licensed to carry colour. The sign IS the
# meaning there; everywhere else the row stays neutral and the result is
# carried by an explicit badge, so nothing depends on colour alone.
MONEY_COLUMNS = ("P&L", "R")

# Breakeven is neither a win nor a loss. These are the formatted forms the
# ledger produces for zero, matched as text because that is what the frame
# carries by the time it reaches the styler.
_BREAKEVEN = ("—", "$0.00", "0.00R")


def format_money(value: object) -> str:
    """Format one optional ledger amount with an explicit currency sign."""
    if value is None or pd.isna(value):
        return "—"
    amount = float(value)
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.2f}"


def demo_ledger_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Present demo rows with the same labels and formats as the real ledger."""
    source = frame.copy()
    session = source.get("session", source.get("killzone"))
    result = source["result"].fillna("").map(humanize)
    return pd.DataFrame(
        {
            "Date": source["trade_date"].fillna("—").astype(str),
            "Asset": source["asset"].fillna("—").astype(str),
            "Direction": source["direction"].fillna("—").map(humanize),
            "Setup": source["setup_type"].fillna("—").map(humanize),
            "Session": session.fillna("—").map(humanize),
            "Result": result.map(
                lambda value: f"{LEDGER_MARKS.get(value, '·')} {value or '—'}"
            ),
            "P&L": source["pnl"].map(format_money),
            "R": source["rr_realized"].map(
                lambda value: "—" if pd.isna(value) else f"{float(value):.2f}R"
            ),
        }
    )


def ledger_row_styles(row) -> list:
    """Per-cell styles for one ledger row, neutral except signed money."""
    styles = [""] * len(row)
    for column in MONEY_COLUMNS:
        if column not in row.index:
            continue
        value = str(row[column])
        if value.startswith("-"):
            colour = TL_DANGER
        elif value in _BREAKEVEN:
            colour = ""
        else:
            colour = TL_SUCCESS
        if colour:
            styles[row.index.get_loc(column)] = f"color: {colour}"
    return styles
