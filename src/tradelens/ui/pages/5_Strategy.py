"""
Strategy Profile — the trader's playbook, and the context every AI review reads.

This is not a settings page. The rules stored here are what grading, the weekly
recap and the pattern lenses compare a trade against, so the page opens with a
compact summary of the saved playbook and how complete it is, then discloses the
rule groups one at a time instead of presenting twelve fields at once.

Post-trade reflection only — these are the trader's own rules, never advice.
"""

import logging
import sys
from html import escape
from pathlib import Path

_root = str(Path(__file__).resolve().parents[4])
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st  # noqa: E402

from src.tradelens.services.strategy import (  # noqa: E402
    get_active_strategy,
    parse_markets,
    parse_setups,
    parse_timeframes,
    upsert_strategy_profile,
)
from src.tradelens.ui.components.auth import current_user_id, require_auth  # noqa: E402
from src.tradelens.ui.components.demo_banner import render_demo_banner  # noqa: E402
from src.tradelens.ui.components.sidebar import render_sidebar  # noqa: E402
from src.tradelens.ui.components.theme import inject_css  # noqa: E402
from src.tradelens.ui.components.ui import error_box  # noqa: E402
from src.tradelens.ui.components.workspace import (  # noqa: E402
    render_workspace_header,
)
from src.tradelens.ui.design_system import (  # noqa: E402
    inject_design_system,
    render_badge,
    render_chip_row,
)

st.set_page_config(page_title="Strategy Profile")
inject_css()
inject_design_system()  # design_system.py wins ties (injected after theme)
require_auth()
uid = current_user_id()
render_demo_banner()
render_sidebar()

st.markdown(
    render_workspace_header(
        "Strategy Profile",
        "Your own rules, written down.",
    ),
    unsafe_allow_html=True,
)

# ── The six sections a playbook is made of ────────────────────────
# Stop-loss and take-profit are one decision — where a trade ends — so they
# share Exit Rules. Setups traded, setups avoided and the session/news filter
# are all "what I will and will not take", so they share Setups. Eight
# disclosures for six ideas was the settings dump.
PLAYBOOK_SECTIONS = (
    "Identity",
    "Entry Rules",
    "Exit Rules",
    "Risk Rules",
    "Setups",
    "Self-Awareness",
)

# Which stored fields count a section as written. Any one of them is enough:
# a trader who states an exit rule but no take-profit target has still made
# that decision.
_SECTION_FIELDS = {
    "Identity": ("name",),
    "Entry Rules": ("entry_rules",),
    "Exit Rules": ("stop_rules", "take_profit_rules"),
    "Risk Rules": ("risk_rules",),
    "Setups": ("setups_traded", "setups_avoided", "news_session_rules"),
    "Self-Awareness": ("common_mistakes",),
}

_NAME_ERROR_KEY = "_strategy_name_error"
_SAVE_ERROR_KEY = "_strategy_save_error"
_STARTER_ERROR_KEY = "_strategy_starter_error"

# Both writes on this page fail the same way, so they say the same thing.
# Driver text can carry a database URL, a dialect message or a fragment of
# the row, so it never reaches the page — see _write().
_WRITE_FAILED = "Could not save the playbook. Try again."

_log = logging.getLogger(__name__)


def _write(error_key: str, **fields) -> bool:
    """Persist the profile. Returns True on success.

    The single protected path for every write on this page: the exception
    goes to the log with its stack, and the trader gets a message they can
    act on. A page that renders str(exc) leaks whatever the driver put in
    it; a page that lets it propagate loses the form.
    """
    try:
        upsert_strategy_profile(uid, **fields)
    except Exception:  # noqa: BLE001 — never crash the page
        _log.exception("strategy profile write failed for user %s", uid)
        st.session_state[error_key] = _WRITE_FAILED
        return False
    st.session_state.pop(error_key, None)
    return True


STARTER_TEMPLATE = {
    "name": "ICT/SMC Day Trading",
    "trading_style": "ICT / SMC",
    "markets": "NQ, ES, EURUSD, GBP/USD",
    "timeframes": "15m entry, 1H/4H HTF",
    "entry_rules": (
        "Wait for HTF POI, confirm BOS or CHoCH on LTF, enter on FVG or OB retest"
    ),
    "stop_rules": "Place SL below/above the swing that caused the BOS",
    "take_profit_rules": "TP at next liquidity level or opposing HTF POI",
    "risk_rules": "Max 1% per trade, max 2 trades per session, no revenge trading",
    "setups_traded": "Liquidity Sweep + FVG, BOS + OB Retest, CHoCH Entry",
    "setups_avoided": (
        "Counter-trend without BOS, news candle entries, off-session trades"
    ),
    "common_mistakes": "FOMO entry, moving SL, off-session trades, overtrading",
}


def _profile_completion(profile: dict) -> tuple:
    """How many of the six sections have been written, and out of how many.

    Completion is read from the SAVED profile, so the figure describes what
    the AI can actually use — not what is currently typed into the form.
    """
    written = 0
    for section in PLAYBOOK_SECTIONS:
        if any(str(profile.get(f) or "").strip() for f in _SECTION_FIELDS[section]):
            written += 1
    return written, len(PLAYBOOK_SECTIONS)


def _facet(label: str, items: list, variant: str) -> str:
    """One read-only row of saved values. Empty facets are omitted entirely
    rather than rendered as a label with nothing beside it."""
    if not items:
        return ""
    return (
        '<div class="tl-playbook-facet">'
        f'<p class="tl-playbook-facet-label">{escape(label)}</p>'
        f"{render_chip_row(items, {c: variant for c in items})}"
        "</div>"
    )


def _render_profile_summary(profile: dict) -> None:
    """The compact functional header: whose playbook, how complete, what
    reads it, and the saved values worth scanning."""
    done, total = _profile_completion(profile)
    name = str(profile.get("name") or "").strip()
    updated = (profile.get("updated_at") or "")[:10]

    timeframes = parse_timeframes(profile)
    parts = [
        '<section class="tl-playbook">',
        '<div class="tl-playbook-head">',
        f'<p class="tl-playbook-name">{escape(name or "No playbook yet")}</p>',
        render_badge("Active", "success") if name else "",
        f'<p class="tl-playbook-meta">Updated {escape(updated)}</p>' if updated else "",
        "</div>",
        '<div class="tl-playbook-progress" aria-hidden="true">'
        f'<span style="width:{round(done / total * 100)}%"></span></div>',
        f'<p class="tl-playbook-count">{done} of {total} sections written</p>',
        '<p class="tl-playbook-why">'
        + (
            "Reviews and grading fall back to generic reflection until you "
            "describe how you trade."
            if done < total
            else "Every review and grade is read against these rules."
        )
        + "</p>",
    ]

    # Three facets, not five. Saved values earn a chip when scanning them is
    # faster than reading the field — which is true of a set of instruments,
    # not of a paragraph. "Setups I avoid" is deliberately absent: the only
    # variant that would distinguish it is red, and red here means an error
    # or a loss, never an ordinary choice the trader made on purpose.
    facets = "".join(
        (
            _facet("Markets", parse_markets(profile), "primary"),
            _facet(
                "Timeframes",
                [
                    f"{label} {value}"
                    for label, value in (
                        ("Entry", timeframes.get("entry")),
                        ("HTF", timeframes.get("htf")),
                    )
                    if value
                ],
                "neutral",
            ),
            _facet("Setups", parse_setups(profile), "primary"),
        )
    )
    if facets:
        parts.append(f'<div class="tl-playbook-facets">{facets}</div>')
    parts.append("</section>")

    st.markdown("".join(parts), unsafe_allow_html=True)


# ── Load, summarize, offer a starting point ───────────────────────
profile = get_active_strategy(uid) if uid is not None else None

if st.session_state.pop("_strategy_saved", False):
    st.toast("Playbook saved — AI reviews will now use your rules.", icon="✅")

_render_profile_summary(profile or {})

# This writes immediately — it is a save, not a draft — so the label, the
# help and the confirmation all say so. Copy that promises a review step
# before anything is stored would be describing a different button.
_starter_clicked = st.button(
    "Apply the ICT/SMC starter playbook",
    key="strategy_starter",
    type="secondary" if profile else "primary",
    disabled=uid is None,
    help=(
        "Saves a complete starter playbook as your active profile; "
        "review and customize it afterward."
    ),
)
# The failure belongs beside the control that caused it, not at the foot of
# a form the trader never touched.
starter_error_slot = st.empty()

if _starter_clicked:
    if _write(_STARTER_ERROR_KEY, **STARTER_TEMPLATE):
        st.toast("Starter playbook saved as your active profile.", icon="✅")
        st.rerun()

if st.session_state.get(_STARTER_ERROR_KEY):
    starter_error_slot.markdown(
        error_box(str(st.session_state[_STARTER_ERROR_KEY])), unsafe_allow_html=True
    )

p = profile or {}

# ── The playbook form ─────────────────────────────────────────────
# Identity is open because it is the one section that cannot be skipped;
# every rule group is an accordion, so the page opens as six lines rather
# than a wall of twelve fields.
#
# The keyed container is what scopes the accordion reveal. Streamlit gives
# every st.expander the same testid, so an unscoped rule would animate the
# Journal's filters, the wizard's screenshot panel, Settings and the auth
# screen too — a page-load flicker on five pages that asked for none.
# st.container(key=…) renders .st-key-tl_playbook_form around this form.
with st.container(key="tl_playbook_form"), st.form("strategy_form"):
    # Two hashes, not five. This is the first heading under the page title
    # and there is no h2 between them, so it IS the h2 — the original h5
    # skipped three levels, and a first correction to h3 still skipped one.
    # Measured in the browser both times; no CSS targets either level, so
    # nothing about the look changes.
    st.markdown(f"## {PLAYBOOK_SECTIONS[0]}")
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input(
            "Strategy Name",
            value=p.get("name") or "",
            placeholder="e.g. ICT OB Strategy",
        )
        # Filled in the same run as the failed submit, so the message lands
        # under the field it is about instead of floating over the page.
        name_error_slot = st.empty()
    with col2:
        trading_style = st.text_input(
            "Trading Style",
            value=p.get("trading_style") or "",
            placeholder="e.g. ICT, SMC, Price Action",
        )

    col3, col4 = st.columns(2)
    with col3:
        markets = st.text_input(
            "Markets / Assets",
            value=p.get("markets") or "",
            placeholder="e.g. NQ, ES, BTCUSD, EURUSD",
        )
    with col4:
        timeframes = st.text_input(
            "Timeframes",
            value=p.get("timeframes") or "",
            placeholder="e.g. 15m, 1H, 4H",
        )

    with st.expander(PLAYBOOK_SECTIONS[1]):
        entry_rules = st.text_area(
            "What has to be true before you enter",
            value=p.get("entry_rules") or "",
            height=100,
            placeholder="e.g. BOS + OB retest on 15m, CHoCH confirmation required",
        )

    with st.expander(PLAYBOOK_SECTIONS[2]):
        stop_rules = st.text_area(
            "Where the stop goes",
            value=p.get("stop_rules") or "",
            height=80,
            placeholder="e.g. Behind the OB wick, no more than 10 points away",
        )
        take_profit_rules = st.text_area(
            "Where you take profit",
            value=p.get("take_profit_rules") or "",
            height=80,
            placeholder="e.g. Next opposing OB, 50% at 1:1 R, runner to 1:3",
        )

    with st.expander(PLAYBOOK_SECTIONS[3]):
        risk_rules = st.text_area(
            "How much you risk, and how often",
            value=p.get("risk_rules") or "",
            height=80,
            placeholder=(
                "e.g. Max 1% per trade, max 2 trades per session, 1:2 R:R minimum"
            ),
        )

    with st.expander(PLAYBOOK_SECTIONS[4]):
        setups_traded = st.text_area(
            "What you trade",
            value=p.get("setups_traded") or "",
            height=80,
            placeholder="e.g. OB retest, FVG fill, liquidity sweep + reversal",
        )
        setups_avoided = st.text_area(
            "What you skip",
            value=p.get("setups_avoided") or "",
            height=80,
            placeholder="e.g. Counter-trend, news events, choppy consolidation",
        )
        news_session_rules = st.text_input(
            "When you stay out",
            value=p.get("news_session_rules") or "",
            placeholder=(
                "e.g. No trades 30 min before/after high-impact news; NY AM only"
            ),
        )

    with st.expander(PLAYBOOK_SECTIONS[5]):
        common_mistakes = st.text_area(
            "What you want reviews to watch for",
            value=p.get("common_mistakes") or "",
            height=100,
            placeholder="e.g. Entering too early before confirmation, revenge trading",
        )

    # Anchored at the end of the form it submits, at its own width. A
    # stretched primary button reads as a banner, not an action.
    submitted = st.form_submit_button("Save playbook", type="primary")
    save_error_slot = st.empty()

if submitted:
    if uid is None:
        st.session_state[_SAVE_ERROR_KEY] = (
            "A database-backed account is required to save a playbook."
        )
    elif not name.strip():
        st.session_state[_NAME_ERROR_KEY] = True
        st.session_state.pop(_SAVE_ERROR_KEY, None)
    else:
        st.session_state.pop(_NAME_ERROR_KEY, None)
        if _write(
            _SAVE_ERROR_KEY,
            name=name.strip(),
            trading_style=trading_style.strip() or None,
            markets=markets.strip() or None,
            timeframes=timeframes.strip() or None,
            entry_rules=entry_rules.strip() or None,
            stop_rules=stop_rules.strip() or None,
            take_profit_rules=take_profit_rules.strip() or None,
            risk_rules=risk_rules.strip() or None,
            setups_traded=setups_traded.strip() or None,
            setups_avoided=setups_avoided.strip() or None,
            news_session_rules=news_session_rules.strip() or None,
            common_mistakes=common_mistakes.strip() or None,
        ):
            st.session_state["_strategy_saved"] = True
            st.rerun()

# Both messages are state, so they survive the rerun a toast would not.
if st.session_state.get(_NAME_ERROR_KEY):
    name_error_slot.markdown(
        '<p class="tl-field-error" role="alert">Strategy name is required — '
        "it is how reviews refer to this playbook.</p>",
        unsafe_allow_html=True,
    )
if st.session_state.get(_SAVE_ERROR_KEY):
    save_error_slot.markdown(
        error_box(str(st.session_state[_SAVE_ERROR_KEY])), unsafe_allow_html=True
    )
