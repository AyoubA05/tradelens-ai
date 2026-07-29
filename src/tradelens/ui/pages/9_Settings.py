"""
Settings — the quietest page in the product.

Nothing here is the work. Preferences, data tools and account controls are
grouped into four sections, saved one at a time with the confirmation beside
the control that changed, and the only bordered object on the page is the
zone holding the two actions that destroy data.

No chart, no banner, no feature promotion, no primary call to action: this
page exists to be finished with.
"""

import logging
import sys
import datetime
from html import escape
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
from src.tradelens.ui.components.workspace import (  # noqa: E402
    render_section_header,
    render_workspace_header,
)
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

SETTINGS_SECTIONS = (
    "Profile",
    "Preferences",
    "Data",
    "Danger Zone",
)

_log = logging.getLogger(__name__)

# Every failure on this page reports the same way: the exception goes to the
# log with its stack, and the trader gets a sentence they can act on. Driver
# text can carry a database URL or a fragment of the row.
_GENERIC_FAILURE = "That did not work. Try again."


def _render_setting_status(saved: bool, message: str) -> None:
    """Inline result of one setting change, beside the control that made it.

    A toast auto-dismisses and appears in a corner the eye is not on;
    settings are changed one at a time, so the confirmation belongs where
    the change happened. role="status" so it is announced rather than only
    seen.
    """
    tone = "ok" if saved else "fail"
    st.markdown(
        f'<p class="tl-setting-status {tone}" role="status">{escape(message)}</p>',
        unsafe_allow_html=True,
    )


def _row(label: str, value: str) -> str:
    return (
        '<div class="tl-settings-row">'
        f'<p class="tl-settings-label">{escape(label)}</p>'
        f'<p class="tl-settings-value">{escape(value)}</p>'
        "</div>"
    )


def _note(text: str) -> None:
    st.markdown(
        f'<p class="tl-settings-note">{escape(text)}</p>', unsafe_allow_html=True
    )


st.markdown(
    render_workspace_header(
        "Settings",
        "Preferences, your data, and your account. Nothing here changes how "
        "your trades are analysed.",
    ),
    unsafe_allow_html=True,
)

_has_settings_owner = isinstance(uid, int) and not isinstance(uid, bool) and uid > 0

# ══════════════════════════════════════════════════════════════════
# Profile — who you are signed in as, and how you get back in
# ══════════════════════════════════════════════════════════════════
st.markdown(
    render_section_header(
        SETTINGS_SECTIONS[0], "Your account and the way back into it."
    ),
    unsafe_allow_html=True,
)

if not _has_settings_owner:
    _note("Account settings are unavailable for this legacy login.")
else:
    _account = get_user_by_id(uid)
    _current_email = (_account.email if _account else None) or ""

    st.markdown(
        _row("Signed in as", str(getattr(_account, "username", "") or "—")),
        unsafe_allow_html=True,
    )

    _email_input = st.text_input(
        "Recovery email",
        value=_current_email,
        placeholder="you@example.com",
        key="settings_email",
        help=(
            "Optional, and the only way back into your account if you forget "
            "your password. Used for nothing else."
        ),
    )
    if st.button("Save recovery email", key="settings_email_save"):
        try:
            _saved = set_email(uid, _email_input)
        except ValueError:
            # A rejected address is the user's own input, so the reason is
            # theirs to see — but it is written here, not taken from the
            # exception, which may carry more than the address.
            st.session_state["_settings_email_status"] = (
                False,
                "That does not look like an email address.",
            )
        except Exception:  # noqa: BLE001 — never crash the page
            _log.exception("recovery email save failed for user %s", uid)
            st.session_state["_settings_email_status"] = (False, _GENERIC_FAILURE)
        else:
            st.session_state["_settings_email_status"] = (
                True,
                "Recovery email saved." if _saved else "Recovery email cleared.",
            )
        st.rerun()

    if "_settings_email_status" in st.session_state:
        _render_setting_status(*st.session_state.pop("_settings_email_status"))
    elif not _current_email:
        st.markdown(
            render_banner(
                "No recovery email set. Without one, a forgotten password "
                "cannot be recovered and the account is lost.",
                "warning",
            ),
            unsafe_allow_html=True,
        )

    if not reset_email_configured():
        _note(
            "Outgoing email is not configured on this deployment yet, so reset "
            "messages cannot be delivered."
        )

_note(
    "Login credentials are managed through deployment secrets "
    "(TRADELENS_USERNAME / TRADELENS_PASSWORD). Contact the admin to change them."
)

# ══════════════════════════════════════════════════════════════════
# Preferences — how the app reads your trades
# ══════════════════════════════════════════════════════════════════
st.markdown(
    render_section_header(SETTINGS_SECTIONS[1], "How the app interprets what you log."),
    unsafe_allow_html=True,
)

_TZ_OPTIONS = [
    "America/New_York",
    "America/Chicago",
    "Europe/London",
    "Asia/Tokyo",
    "Asia/Dubai",
    "UTC",
]
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
    try:
        set_timezone(uid, _chosen_tz)
    except Exception:  # noqa: BLE001 — never crash the page
        _log.exception("timezone save failed for user %s", uid)
        _render_setting_status(False, _GENERIC_FAILURE)
    else:
        _render_setting_status(True, f"Trading timezone saved — {_chosen_tz}.")
elif not _has_settings_owner:
    _note("Trading timezone preferences are unavailable for this legacy login.")

# AI is an optional integration. Unconfigured is a state with an action
# attached, not an error, so it gets a neutral dot rather than a red panel.
if has_api_key():
    _ai_state, _ai_on = "AI features are enabled — an API key is configured.", True
elif is_demo():
    _ai_state, _ai_on = (
        "Demo mode — AI sections read cached sample responses. No key, no spend.",
        True,
    )
else:
    _ai_state, _ai_on = (
        "AI features are off until an API key is configured.",
        False,
    )
st.markdown(
    f'<p class="tl-settings-state{" on" if _ai_on else ""}">'
    f"{escape(_ai_state)}</p>",
    unsafe_allow_html=True,
)
with st.expander("How to configure an API key"):
    st.markdown(
        """
1. Get an API key from **Anthropic** (console.anthropic.com).
2. In **Streamlit Cloud**: **App Settings → Secrets**, then add:
   ```
   ANTHROPIC_API_KEY = "your-key-here"
   ```
3. **Locally**: add the key to `.streamlit/secrets.toml` or `.env`.
4. Restart the app.
"""
    )

# ══════════════════════════════════════════════════════════════════
# Data — what you can take out, put in, and what the AI has cost
# ══════════════════════════════════════════════════════════════════
st.markdown(
    render_section_header(
        SETTINGS_SECTIONS[2], "Your records, in and out — and what AI has cost."
    ),
    unsafe_allow_html=True,
)

trades = get_trades(user_id=uid)
df_export = pd.DataFrame(
    [{col: getattr(t, col, None) for col in CSV_COLUMNS} for t in trades]
)
csv_bytes = export_trades_csv(df_export)

exp_col, imp_col = st.columns(2)
with exp_col:
    st.download_button(
        label=f"Export {len(df_export)} trades as CSV",
        data=csv_bytes,
        file_name="trades.csv",
        mime="text/csv",
    )
with imp_col:
    uploaded = st.file_uploader("Import trades from CSV", type=["csv"])
    if uploaded is not None:
        try:
            rows_inserted, skipped, errors = import_trades_csv(uploaded, user_id=uid)
        except Exception:  # noqa: BLE001 — never crash the page
            _log.exception("csv import failed for user %s", uid)
            _render_setting_status(False, _GENERIC_FAILURE)
        else:
            if rows_inserted or skipped:
                _render_setting_status(
                    True,
                    f"Imported {rows_inserted} trades, skipped {skipped} duplicates.",
                )
            elif not errors:
                _render_setting_status(True, "That CSV was valid but had no rows.")
            for err in errors:
                st.warning(err)

_note("Export first to see the column format an import expects.")

sample_count = count_sample_trades(uid)
load_col, clear_col = st.columns(2)
with load_col:
    if st.button("Load sample trades", key="settings_sample_load"):
        try:
            st.session_state["_sample_status"] = (
                True,
                f"Loaded {load_sample_trades(uid)} sample trades.",
            )
        except Exception:  # noqa: BLE001 — never crash the page
            _log.exception("sample load failed for user %s", uid)
            st.session_state["_sample_status"] = (False, _GENERIC_FAILURE)
        st.rerun()
with clear_col:
    if st.button(
        "Clear sample trades",
        key="settings_sample_clear",
        disabled=sample_count == 0,
    ):
        try:
            st.session_state["_sample_status"] = (
                True,
                f"Removed {clear_sample_trades(uid)} sample trades.",
            )
        except Exception:  # noqa: BLE001 — never crash the page
            _log.exception("sample clear failed for user %s", uid)
            st.session_state["_sample_status"] = (False, _GENERIC_FAILURE)
        st.rerun()

if "_sample_status" in st.session_state:
    _render_setting_status(*st.session_state.pop("_sample_status"))
_note(
    f"{sample_count} sample trades are loaded. They are flagged as samples and "
    "clearing them never touches a trade you logged."
)

if not _has_settings_owner:
    _note("AI cost history is unavailable for this legacy login.")
else:
    _today = datetime.date.today()
    _cost_df = monthly_cost_by_feature(_today.year, _today.month, user_id=uid)
    if _cost_df.empty:
        _note("No AI spend recorded this month.")
    else:
        _disp = _cost_df.copy()
        _total = float(_disp["cost_usd"].sum())
        _disp["cost_usd"] = _disp["cost_usd"].apply(lambda v: f"${v:.4f}")
        _disp = _disp.rename(
            columns={"feature": "Feature", "cost_usd": "Cost", "calls": "Calls"}
        )
        st.dataframe(_disp, hide_index=True)
        _note(f"AI spend this month: ${_total:.4f}.")

# ══════════════════════════════════════════════════════════════════
# Danger Zone — the only bordered object on the page
# ══════════════════════════════════════════════════════════════════
with st.container(key="tl_danger_zone"):
    st.markdown(
        '<section class="tl-danger-zone">'
        f'<p class="tl-danger-zone-title">{escape(SETTINGS_SECTIONS[3])}</p>'
        '<p class="tl-danger-zone-lede">Both of these are permanent, take '
        "effect immediately, and have no backup. Each one asks you to type "
        "its confirmation in full.</p></section>",
        unsafe_allow_html=True,
    )

    with st.expander("Delete all trades"):
        _note(
            "Permanently deletes every trade you have logged, sample and real. "
            "Your account, playbook and settings are kept. Export your trades "
            "first if you want to keep them."
        )
        if not _has_settings_owner:
            _note("Trade deletion is unavailable for this legacy login.")
        typed = st.text_input(
            "Type DELETE to confirm",
            key="danger_confirm",
            disabled=not _has_settings_owner,
        )
        if st.button(
            "Delete all trades permanently",
            key="secondary_delete_trades",
            disabled=not _has_settings_owner or typed != "DELETE",
        ):
            try:
                deleted = delete_all_trades(uid)
            except Exception:  # noqa: BLE001 — never crash the page
                _log.exception("delete-all-trades failed for user %s", uid)
                _render_setting_status(False, _GENERIC_FAILURE)
            else:
                _render_setting_status(True, f"Deleted {deleted} trades.")

    with st.expander("Delete my account"):
        _note(
            "Permanently deletes your account and everything in it: every "
            "trade, note and psychology entry, your Strategy Profile, your "
            "saved reviews and AI analyses, your settings, and every chart "
            "image you uploaded. It cannot be undone and there is no backup. "
            "Export your trades first if you want to keep them."
        )
        _note(
            "Anonymous records of what AI features cost to run are kept for "
            "accounting, with no link to you or your trades."
        )
        if not _has_settings_owner:
            _note("Account deletion is unavailable for this legacy login.")

        _confirm_account = st.text_input(
            "Type DELETE MY ACCOUNT to confirm",
            key="danger_account_confirm",
            disabled=not _has_settings_owner,
        )
        if st.button(
            "Delete my account permanently",
            key="secondary_delete_account",
            disabled=not _has_settings_owner
            or _confirm_account.strip() != "DELETE MY ACCOUNT",
        ):
            try:
                if delete_account(uid):
                    sign_out()
                    st.stop()
                else:
                    _render_setting_status(False, "That account no longer exists.")
            except Exception:  # noqa: BLE001 — never crash the page
                _log.exception("account deletion failed for user %s", uid)
                _render_setting_status(False, _GENERIC_FAILURE)
