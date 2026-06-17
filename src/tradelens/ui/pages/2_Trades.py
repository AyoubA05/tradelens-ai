import sys
from pathlib import Path

# parents[4] of src/tradelens/ui/pages/2_Trades.py  →  project root
_root = str(Path(__file__).resolve().parents[4])
if _root not in sys.path:
    sys.path.insert(0, _root)

import datetime  # noqa: E402

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src.tradelens.services.trade_service import get_trades  # noqa: E402

st.set_page_config(page_title="Trade Journal", page_icon="📒")

st.title("📒 Trade Journal")

# --- Filter row ---
col1, col2, col3, col4 = st.columns([2, 2, 2, 2])

with col1:
    today = datetime.date.today()
    start_date = st.date_input("From", value=today - datetime.timedelta(days=30))
    end_date = st.date_input("To", value=today)

with col2:
    asset_filter = st.text_input("Asset", placeholder="All")

with col3:
    result_filter = st.selectbox("Result", ["All", "Win", "Loss", "Breakeven"])

with col4:
    session_filter = st.selectbox("Session", ["All", "London", "NY AM", "NY PM", "Asia"])


# --- Load trades ---
trades = get_trades(
    start_date=str(start_date),
    end_date=str(end_date),
    asset=asset_filter or None,
    result=result_filter,
    session=session_filter,
)

if not trades:
    st.info("No trades found. Log your first trade on the New Trade page.")
    st.stop()

# --- Build DataFrame ---
DISPLAY_COLS = [
    "trade_date", "asset", "direction", "setup_type",
    "result", "pnl", "rr_realized", "strategy_used", "notes",
]

rows = []
for t in trades:
    rows.append({
        "trade_date": t.trade_date,
        "asset": t.asset,
        "direction": t.direction,
        "setup_type": t.setup_type,
        "result": t.result,
        "pnl": t.pnl if t.pnl is not None else 0.0,
        "rr_realized": t.rr_realized,
        "strategy_used": t.strategy_used,
        "notes": (t.notes or "")[:40] if t.notes else "",
    })

df = pd.DataFrame(rows, columns=DISPLAY_COLS)

# --- Summary line ---
total_pnl = df["pnl"].sum()
wins = (df["result"] == "Win").sum()
total = len(df)
win_rate = wins / total if total > 0 else 0.0

st.markdown(
    f"**Showing {total} trades** &nbsp;|&nbsp; "
    f"Total P/L: **${total_pnl:,.2f}** &nbsp;|&nbsp; "
    f"Win Rate: **{win_rate:.0%}**"
)

# --- Column config ---
col_cfg = {
    "trade_date": st.column_config.TextColumn("Date"),
    "asset": st.column_config.TextColumn("Asset"),
    "direction": st.column_config.TextColumn("Direction"),
    "setup_type": st.column_config.TextColumn("Setup"),
    "result": st.column_config.TextColumn("Result"),
    "pnl": st.column_config.NumberColumn(
        "P&L ($)",
        format="$%.2f",
    ),
    "rr_realized": st.column_config.NumberColumn(
        "RR Realized",
        format="%.2fR",
    ),
    "strategy_used": st.column_config.TextColumn("Strategy"),
    "notes": st.column_config.TextColumn("Notes"),
}

st.dataframe(df, column_config=col_cfg, use_container_width=True, hide_index=True)
