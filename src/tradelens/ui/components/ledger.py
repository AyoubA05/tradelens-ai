"""Pure presentation helpers for the Journal ledger.

No Streamlit import. `2_Trades.py` runs its whole script at module scope, so a
unit test that imports the page boots a page and needs a database — the same
reason Tasks 5-7 put the Overview's band logic in `overview_bands.py` rather
than in `app.py`. The row-styling rule is a real contract (spec 6.3: neutral
by row, semantic colour only on signed money), so it lives where a test can
reach it directly.
"""

from __future__ import annotations

from src.tradelens.ui.design_system import TL_DANGER, TL_SUCCESS

# Money columns are the only ones licensed to carry colour. The sign IS the
# meaning there; everywhere else the row stays neutral and the result is
# carried by an explicit badge, so nothing depends on colour alone.
MONEY_COLUMNS = ("P&L", "R")

# Breakeven is neither a win nor a loss. These are the formatted forms the
# ledger produces for zero, matched as text because that is what the frame
# carries by the time it reaches the styler.
_BREAKEVEN = ("—", "$0.00", "0.00R")


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
