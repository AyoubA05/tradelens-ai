import sys
import datetime
from pathlib import Path

# parents[4] of src/tradelens/ui/pages/9_Settings.py  →  project root
_root = str(Path(__file__).resolve().parents[4])
if _root not in sys.path:
    sys.path.insert(0, _root)

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src.tradelens.db.models import Trade  # noqa: E402
from src.tradelens.db.session import SessionLocal  # noqa: E402
from src.tradelens.services.ai_client import has_api_key  # noqa: E402
from src.tradelens.services.app_settings import (  # noqa: E402
    get_timezone,
    set_timezone,
)
from src.tradelens.services.cost import monthly_cost_by_feature  # noqa: E402
from src.tradelens.services.csvio import (  # noqa: E402
    CSV_COLUMNS,
    export_trades_csv,
    import_trades_csv,
)
from src.tradelens.services.sample_data import (  # noqa: E402
    clear_sample_trades,
    count_sample_trades,
    load_sample_trades,
)
from src.tradelens.services.trade_service import get_trades  # noqa: E402
from src.tradelens.ui.components.auth import (  # noqa: E402
    current_user_id,
    require_auth,
)
from src.tradelens.ui.components.demo_banner import render_demo_banner  # noqa: E402
from src.tradelens.ui.components.sidebar import render_sidebar  # noqa: E402
from src.tradelens.ui.components.theme import inject_css  # noqa: E402
from src.tradelens.ui.components.ui import section_header  # noqa: E402

st.set_page_config(page_title="Settings")
inject_css()
require_auth()
render_demo_banner()
render_sidebar()
st.markdown(section_header("Settings"), unsafe_allow_html=True)

# ── AI Status ─────────────────────────────────────────────────────
st.subheader("AI Status")
if has_api_key():
    st.markdown(
        '<div style="background:rgba(46,125,50,0.15);border:1px solid #2e7d32;'
        'border-radius:8px;padding:10px 14px;color:#7bd88f">'
        "✅ <strong>AI Enabled</strong> — API key is configured.</div>",
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        '<div style="background:rgba(168,75,47,0.15);border:1px solid #A84B2F;'
        'border-radius:8px;padding:10px 14px;color:#e0855f">'
        "❌ <strong>AI Disabled</strong> — API key not found.</div>",
        unsafe_allow_html=True,
    )

with st.expander("How to enable AI"):
    st.markdown(
        """
To enable AI screenshot analysis:

1. Get an API key from **Anthropic** (console.anthropic.com).
2. In **Streamlit Cloud**: go to **App Settings → Secrets** and add:
   ```
   ANTHROPIC_API_KEY = "your-key-here"
   ```
3. **Locally**: add the key to `.streamlit/secrets.toml` or `.env`.
4. Restart the app.

This app uses Anthropic — the key name is `ANTHROPIC_API_KEY`.
"""
    )

st.divider()

# ── Preferences ───────────────────────────────────────────────────
st.subheader("Preferences")
_TZ_OPTIONS = [
    "America/New_York",
    "America/Chicago",
    "Europe/London",
    "Asia/Tokyo",
    "Asia/Dubai",
    "UTC",
]
_current_tz = get_timezone()
_tz_index = _TZ_OPTIONS.index(_current_tz) if _current_tz in _TZ_OPTIONS else 0
_chosen_tz = st.selectbox(
    "Trading timezone",
    _TZ_OPTIONS,
    index=_tz_index,
    key="settings_timezone",
    help="Used to detect your killzone/session from the entry time on New Trade.",
)
if _chosen_tz != _current_tz:
    set_timezone(_chosen_tz)
    st.toast("Trading timezone saved", icon="✅")

st.divider()

# ── Data Management ───────────────────────────────────────────────
st.subheader("Data Management")

trades = get_trades(user_id=current_user_id())
df_export = pd.DataFrame(
    [{col: getattr(t, col, None) for col in CSV_COLUMNS} for t in trades]
)
csv_bytes = export_trades_csv(df_export)

exp_col, imp_col = st.columns(2)
with exp_col:
    st.markdown("**Export trades**")
    st.caption(f"{len(df_export)} trades")
    st.download_button(
        label="Download trades.csv",
        data=csv_bytes,
        file_name="trades.csv",
        mime="text/csv",
        use_container_width=True,
    )
with imp_col:
    st.markdown("**Import trades**")
    st.caption("Tip: Export first to see the required column format.")
    uploaded = st.file_uploader("Upload trades CSV", type=["csv"])
    if uploaded is not None:
        rows_inserted, skipped, errors = import_trades_csv(
            uploaded, user_id=current_user_id()
        )
        if rows_inserted or skipped:
            st.toast(
                f"Imported {rows_inserted} trades. Skipped {skipped} duplicates.",
                icon="✅",
            )
        for err in errors:
            st.warning(err)
        if rows_inserted == 0 and skipped == 0 and not errors:
            st.caption("CSV was valid but contained no rows.")

st.markdown("")

# ── Sample data ───────────────────────────────────────────────────
sample_count = count_sample_trades(current_user_id())
st.markdown("**Demo Data**")
st.caption(
    f"Sample trades currently loaded: {sample_count}. "
    "Sample trades are clearly flagged and can be cleared without affecting "
    "your real trades."
)
load_col, clear_col = st.columns(2)
with load_col:
    if st.button("Load sample trades", use_container_width=True):
        st.session_state["_sample_loaded_n"] = load_sample_trades(current_user_id())
        st.rerun()
with clear_col:
    if st.button(
        "Clear sample trades",
        use_container_width=True,
        disabled=sample_count == 0,
    ):
        removed = clear_sample_trades(current_user_id())
        st.toast(f"Removed {removed} demo trades", icon="✅")
        st.rerun()

if st.session_state.get("_sample_loaded_n"):
    n_loaded = st.session_state.pop("_sample_loaded_n")
    st.markdown(
        '<div style="background:rgba(46,125,50,0.15);border:1px solid #2e7d32;'
        'border-radius:8px;padding:10px 14px;color:#7bd88f">'
        f"✅ Loaded {n_loaded} sample trades. Go to Dashboard to view analytics."
        "</div>",
        unsafe_allow_html=True,
    )
    if st.button("Open Dashboard →", type="primary"):
        st.switch_page("app.py")

st.divider()

# ── AI Cost (current month) ───────────────────────────────────────
st.subheader("AI Cost — This Month")
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

st.divider()

# ── Login / Secrets ───────────────────────────────────────────────
st.subheader("Login & Secrets")
st.caption(
    "Credentials are managed via Streamlit secrets "
    "(`TRADELENS_USERNAME` / `TRADELENS_PASSWORD`). "
    "Contact the admin to change login credentials."
)

st.divider()

# ── Danger Zone ───────────────────────────────────────────────────
st.subheader("Danger Zone")
with st.expander("Delete all trades", expanded=False):
    st.warning(
        "This will **permanently delete all your trades** (sample and real). "
        "Type **DELETE** to confirm."
    )
    typed = st.text_input("Type DELETE to confirm", key="danger_confirm")
    if st.button(
        "Delete ALL trades",
        type="primary",
        disabled=typed != "DELETE",
    ):
        db = SessionLocal()
        try:
            deleted = db.query(Trade).delete()
            db.commit()
            st.toast(f"Deleted {deleted} trade(s)", icon="✅")
        except Exception as exc:
            db.rollback()
            st.toast(f"Delete failed: {exc}", icon="❌")
        finally:
            db.close()
