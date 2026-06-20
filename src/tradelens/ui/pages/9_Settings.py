import sys
import datetime
from pathlib import Path

# parents[4] of src/tradelens/ui/pages/7_Settings.py  →  project root
_root = str(Path(__file__).resolve().parents[4])
if _root not in sys.path:
    sys.path.insert(0, _root)

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src.tradelens.db.models import Trade  # noqa: E402
from src.tradelens.db.session import SessionLocal  # noqa: E402
from src.tradelens.services.cost import monthly_cost_by_feature  # noqa: E402
from src.tradelens.services.csvio import (
    CSV_COLUMNS,
    export_trades_csv,
    import_trades_csv,
)  # noqa: E402
from src.tradelens.services.trade_service import get_trades  # noqa: E402

st.set_page_config(page_title="Settings", page_icon="⚙️")
st.title("⚙️ Settings")

# ── Export Trades ─────────────────────────────────────────────────
st.subheader("📤 Export Trades")

trades = get_trades()
df_export = pd.DataFrame(
    [{col: getattr(t, col, None) for col in CSV_COLUMNS} for t in trades]
)

csv_bytes = export_trades_csv(df_export)

st.caption(f"Exporting {len(df_export)} trades")
st.download_button(
    label="Download trades.csv",
    data=csv_bytes,
    file_name="trades.csv",
    mime="text/csv",
    use_container_width=True,
)

st.markdown("---")

# ── Import Trades ─────────────────────────────────────────────────
st.subheader("📥 Import Trades")
st.caption("Tip: Export first to see the required column format.")

uploaded = st.file_uploader("Upload trades CSV", type=["csv"])

if uploaded is not None:
    rows_inserted, errors = import_trades_csv(uploaded)
    if rows_inserted:
        st.success(f"Imported {rows_inserted} trades successfully.")
    if errors:
        for err in errors:
            st.warning(err)
    if rows_inserted == 0 and not errors:
        st.info("CSV was valid but contained no rows.")

st.markdown("---")

# ── AI Cost (current month) ───────────────────────────────────────
st.subheader("💸 AI Cost — This Month")
_today = datetime.date.today()
_cost_df = monthly_cost_by_feature(_today.year, _today.month)
if _cost_df.empty:
    st.caption("No AI spend recorded this month.")
else:
    _disp = _cost_df.copy()
    _total = float(_disp["cost_usd"].sum())
    _disp["cost_usd"] = _disp["cost_usd"].apply(lambda v: f"${v:.4f}")
    _disp = _disp.rename(
        columns={"feature": "Feature", "cost_usd": "Cost", "calls": "Calls"}
    )
    st.dataframe(_disp, hide_index=True, use_container_width=True)
    st.caption(f"Total this month: ${_total:.4f}")
st.caption(
    "Pattern detection and the AI Partner are per-session and not persisted, "
    "so they are not shown here (tracked for Week 6)."
)

st.markdown("---")

# ── Danger Zone ───────────────────────────────────────────────────
with st.expander("⚠️ Danger Zone", expanded=False):
    confirmed = st.checkbox("I understand this will delete ALL trades")
    if st.button("Delete ALL trades", type="primary", disabled=not confirmed):
        db = SessionLocal()
        try:
            deleted = db.query(Trade).delete()
            db.commit()
            st.success(f"Deleted {deleted} trade(s). The database is now empty.")
        except Exception as exc:
            db.rollback()
            st.error(f"Delete failed: {exc}")
        finally:
            db.close()
