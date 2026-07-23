import sys
import datetime
from pathlib import Path

# parents[4] of src/tradelens/ui/pages/9_Settings.py  →  project root
_root = str(Path(__file__).resolve().parents[4])
if _root not in sys.path:
    sys.path.insert(0, _root)

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src.tradelens.services.ai_client import has_api_key  # noqa: E402
from src.tradelens.services.app_settings import (  # noqa: E402
    DEFAULT_TIMEZONE,
    get_timezone,
    set_timezone,
)
from src.tradelens.services.cost import monthly_cost_by_feature  # noqa: E402
from src.tradelens.services.demo import is_demo  # noqa: E402
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
from src.tradelens.services.trade_service import (  # noqa: E402
    delete_all_trades,
    get_trades,
)
from src.tradelens.ui.components.auth import (  # noqa: E402
    current_user_id,
    require_auth,
)
from src.tradelens.ui.components.demo_banner import render_demo_banner  # noqa: E402
from src.tradelens.ui.components.sidebar import render_sidebar  # noqa: E402
from src.tradelens.ui.components.theme import inject_css  # noqa: E402
from src.tradelens.ui.components.ui import section_header  # noqa: E402
from src.tradelens.ui.design_system import inject_design_system  # noqa: E402

st.set_page_config(page_title="Settings")
inject_css()
inject_design_system()  # design_system.py wins ties (injected after theme)
require_auth()
uid = current_user_id()
render_demo_banner()
render_sidebar()
st.markdown(section_header("Settings"), unsafe_allow_html=True)

# ── AI Status ─────────────────────────────────────────────────────
st.subheader("AI Status")
if has_api_key():
    st.markdown(
        '<div style="background:var(--tl-success-dim);'
        "border:1px solid var(--tl-success);"
        'border-radius:8px;padding:10px 14px;color:var(--tl-success)">'
        "✅ <strong>AI Enabled</strong> — API key is configured.</div>",
        unsafe_allow_html=True,
    )
elif is_demo():
    st.markdown(
        '<div style="background:var(--tl-primary-dim);'
        "border:1px solid var(--tl-primary);"
        'border-radius:8px;padding:10px 14px;color:var(--tl-primary)">'
        "🔬 <strong>Demo mode</strong> — AI sections run on cached sample "
        "responses. No key needed, zero spend.</div>",
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        '<div style="background:var(--tl-danger-dim);'
        "border:1px solid var(--tl-danger);"
        'border-radius:8px;padding:10px 14px;color:var(--tl-danger)">'
        "❌ <strong>AI Disabled</strong> — API key not found.</div>",
        unsafe_allow_html=True,
    )

with st.expander("How to enable AI"):
    st.markdown(
        """
To enable AI features (screenshot review, journal, grading, debriefs, chat):

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
_has_settings_owner = isinstance(uid, int) and not isinstance(uid, bool) and uid > 0
_current_tz = get_timezone(uid) if _has_settings_owner else DEFAULT_TIMEZONE
_tz_index = _TZ_OPTIONS.index(_current_tz) if _current_tz in _TZ_OPTIONS else 0
_chosen_tz = st.selectbox(
    "Trading timezone",
    _TZ_OPTIONS,
    index=_tz_index,
    key="settings_timezone",
    help="Used to detect your killzone/session from the entry time on New Trade.",
    disabled=not _has_settings_owner,
)
if _has_settings_owner and _chosen_tz != _current_tz:
    set_timezone(uid, _chosen_tz)
    st.toast("Trading timezone saved", icon="✅")
elif not _has_settings_owner:
    st.caption("Trading timezone preferences are unavailable for this legacy login.")

st.divider()

# ── Data Management ───────────────────────────────────────────────
st.subheader("Data Management")

trades = get_trades(user_id=uid)
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
        width="stretch",
    )
with imp_col:
    st.markdown("**Import trades**")
    st.caption("Tip: Export first to see the required column format.")
    uploaded = st.file_uploader("Upload trades CSV", type=["csv"])
    if uploaded is not None:
        rows_inserted, skipped, errors = import_trades_csv(uploaded, user_id=uid)
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
sample_count = count_sample_trades(uid)
st.markdown("**Demo Data**")
st.caption(
    f"Sample trades currently loaded: {sample_count}. "
    "Sample trades are clearly flagged and can be cleared without affecting "
    "your real trades."
)
load_col, clear_col = st.columns(2)
with load_col:
    if st.button("Load sample trades", width="stretch"):
        st.session_state["_sample_loaded_n"] = load_sample_trades(uid)
        st.rerun()
with clear_col:
    if st.button(
        "Clear sample trades",
        width="stretch",
        disabled=sample_count == 0,
    ):
        removed = clear_sample_trades(uid)
        st.toast(f"Removed {removed} demo trades", icon="✅")
        st.rerun()

if st.session_state.get("_sample_loaded_n"):
    n_loaded = st.session_state.pop("_sample_loaded_n")
    st.markdown(
        '<div style="background:var(--tl-success-dim);'
        "border:1px solid var(--tl-success);"
        'border-radius:8px;padding:10px 14px;color:var(--tl-success)">'
        f"✅ Loaded {n_loaded} sample trades. Go to Dashboard to view analytics."
        "</div>",
        unsafe_allow_html=True,
    )
    if st.button("Open Dashboard →", type="primary"):
        st.switch_page("app.py")

st.divider()

# ── AI Cost (current month) ───────────────────────────────────────
st.subheader("AI Cost — This Month")
if not _has_settings_owner:
    st.caption("AI cost history is unavailable for this legacy login.")
else:
    _today = datetime.date.today()
    _cost_df = monthly_cost_by_feature(_today.year, _today.month, user_id=uid)
    if _cost_df.empty:
        st.caption("No AI spend recorded this month.")
    else:
        _disp = _cost_df.copy()
        _total = float(_disp["cost_usd"].sum())
        _disp["cost_usd"] = _disp["cost_usd"].apply(lambda v: f"${v:.4f}")
        _disp = _disp.rename(
            columns={"feature": "Feature", "cost_usd": "Cost", "calls": "Calls"}
        )
        st.dataframe(_disp, hide_index=True, width="stretch")
        st.caption(f"Total this month: ${_total:.4f}")

st.divider()

# ── Login / Secrets ───────────────────────────────────────────────
st.subheader("Login")
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
    if not _has_settings_owner:
        st.caption("Trade deletion is unavailable for this legacy login.")
    typed = st.text_input(
        "Type DELETE to confirm",
        key="danger_confirm",
        disabled=not _has_settings_owner,
    )
    if st.button(
        "Delete ALL trades",
        type="primary",
        disabled=not _has_settings_owner or typed != "DELETE",
    ):
        try:
            deleted = delete_all_trades(uid)
            st.toast(f"Deleted {deleted} trade(s)", icon="✅")
        except Exception as exc:
            st.toast(f"Delete failed: {exc}", icon="❌")
