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
from src.tradelens.services.account import delete_account  # noqa: E402
from src.tradelens.services.password_reset import (  # noqa: E402
    email_configured as reset_email_configured,
)
from src.tradelens.services.users import get_user_by_id, set_email  # noqa: E402
from src.tradelens.ui.components.auth import (  # noqa: E402
    current_user_id,
    require_auth,
    sign_out,
)
from src.tradelens.ui.components.demo_banner import render_demo_banner  # noqa: E402
from src.tradelens.ui.components.sidebar import render_sidebar  # noqa: E402
from src.tradelens.ui.components.theme import inject_css  # noqa: E402
from src.tradelens.ui.components.ui import section_header  # noqa: E402
from src.tradelens.ui.design_system import (  # noqa: E402
    inject_design_system,
    render_banner,
)

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

# ── Account ───────────────────────────────────────────────────────
st.subheader("Account")

if not _has_settings_owner:
    st.caption("Account settings are unavailable for this legacy login.")
else:
    _account = get_user_by_id(uid)
    _current_email = (_account.email if _account else None) or ""

    st.markdown("**Recovery email**")
    st.caption(
        "Optional, and the only way back into your account if you forget "
        "your password. Used for nothing else — no newsletters, no sharing."
    )
    if not _current_email:
        st.markdown(
            render_banner(
                "No recovery email set. Without one, a forgotten password "
                "cannot be recovered and the account is lost.",
                "warning",
            ),
            unsafe_allow_html=True,
        )

    _email_input = st.text_input(
        "Email address",
        value=_current_email,
        placeholder="you@example.com",
        key="settings_email",
    )
    if st.button("Save email", key="settings_email_save"):
        try:
            saved = set_email(uid, _email_input)
        except ValueError as exc:
            st.markdown(render_banner(str(exc), "danger"), unsafe_allow_html=True)
        else:
            st.toast(
                "Recovery email saved" if saved else "Recovery email cleared",
                icon="✅",
            )
            st.rerun()

    if not reset_email_configured():
        st.caption(
            "Note: outgoing email is not configured on this deployment yet, "
            "so password reset messages cannot be delivered."
        )

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

with st.expander("Delete my account", expanded=False):
    st.warning(
        "This permanently deletes **your account and everything in it**: "
        "every trade, note, and psychology entry, your Strategy Profile, "
        "your saved reviews and AI analyses, your settings, and every chart "
        "image you uploaded. It cannot be undone and there is no backup. "
        "Export your trades first if you want to keep them."
    )
    st.caption(
        "Anonymous records of what AI features cost to run are kept for "
        "accounting, with no link to you or your trades."
    )
    if not _has_settings_owner:
        st.caption("Account deletion is unavailable for this legacy login.")

    _confirm_account = st.text_input(
        "Type DELETE MY ACCOUNT to confirm",
        key="danger_account_confirm",
        disabled=not _has_settings_owner,
    )
    if st.button(
        "Permanently delete my account",
        key="secondary_delete_account",
        disabled=not _has_settings_owner
        or _confirm_account.strip() != "DELETE MY ACCOUNT",
    ):
        try:
            if delete_account(uid):
                sign_out()
                st.stop()
            else:
                st.toast("Account not found", icon="❌")
        except Exception as exc:  # noqa: BLE001 — never crash the page
            st.toast(f"Delete failed: {exc}", icon="❌")
