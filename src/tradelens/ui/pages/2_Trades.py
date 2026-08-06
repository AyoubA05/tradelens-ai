import sys
from pathlib import Path

# parents[4] of src/tradelens/ui/pages/2_Trades.py  →  project root
_root = str(Path(__file__).resolve().parents[4])
if _root not in sys.path:
    sys.path.insert(0, _root)

import datetime  # noqa: E402
import json  # noqa: E402
from html import escape  # noqa: E402

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src.tradelens.services.cost import log_ai_usage  # noqa: E402
from src.tradelens.services.debrief import (  # noqa: E402
    DebriefError,
    generate_debrief,
)
from src.tradelens.services.demo import get_demo_df, is_demo  # noqa: E402
from src.tradelens.services.screenshot_service import save_screenshot  # noqa: E402
from src.tradelens.services.strategy import get_active_strategy  # noqa: E402
from src.tradelens.services.trade_service import (  # noqa: E402
    delete_trade,
    get_trade,
    get_trades,
    update_trade,
)
from src.tradelens.services.trade_validation import OutcomeMismatch  # noqa: E402
from src.tradelens.ui.components.ai_review import render_ai_review  # noqa: E402
from src.tradelens.ui.components.auth import current_user_id, require_auth  # noqa: E402
from src.tradelens.ui.components.ai_trade_chat import render_ask_ai  # noqa: E402
from src.tradelens.ui.components.corrections_sidebar import (  # noqa: E402
    render_corrections_sidebar,
)
from src.tradelens.ui.components.demo_banner import render_demo_banner  # noqa: E402
from src.tradelens.ui.components.ledger import ledger_row_styles  # noqa: E402
from src.tradelens.ui.components.screenshot_analyzer import (  # noqa: E402
    render_screenshot_analyzer,
)
from src.tradelens.ui.components.sidebar import render_sidebar  # noqa: E402
from src.tradelens.ui.components.theme import inject_css  # noqa: E402
from src.tradelens.ui.components.trade_calendar import (  # noqa: E402
    render_trade_calendar,
)
from src.tradelens.ui.components.workspace import (  # noqa: E402
    EvidenceItem,
    render_evidence_rail,
    render_filter_summary,
    render_section_header,
    render_workspace_header,
)
from src.tradelens.ui.design_system import (  # noqa: E402
    inject_design_system,
    render_badge,
    render_banner,
    render_chip_row,
    render_empty_state,
)
from src.tradelens.utils.ai_utils import ai_available  # noqa: E402
from src.tradelens.utils.format import humanize  # noqa: E402

st.set_page_config(page_title="Journal", layout="wide")
inject_css()
inject_design_system()  # design_system.py wins ties (injected after theme)
require_auth()
uid = current_user_id()
_strategy_profile = get_active_strategy(uid) if uid is not None else None
render_demo_banner()
render_sidebar()
render_corrections_sidebar()

# ── Views ─────────────────────────────────────────────────────────
# One destination, three ways of working the same trades: scan them, find
# them by date, or read one closely. They are views rather than sections
# because stacking all three down one page is the wall this replaces.
JOURNAL_VIEWS = ("Trades", "Calendar", "Trade Detail")
# The view a trader is on is stored SEPARATELY from the selector widget.
# Streamlit forbids writing a widget's own key once that widget has been
# instantiated, so "open this trade" — which happens further down the page,
# long after the selector exists — cannot set the selector's key directly.
# It records an intent instead, and the intent is applied at the top of the
# next run, before any widget is created.
_VIEW_KEY = "journal_view"
_VIEW_WIDGET_KEY = "journal_view_pick"
_GOTO_KEY = "_journal_goto"

_RESULT_VARIANT = {"win": "success", "loss": "danger", "breakeven": "neutral"}

# The semantic edge. A glyph, not a fill: it survives greyscale, colour
# blindness, and a printed page, and it does not shout on every row.
_LEDGER_MARKS = {"Win": "▲", "Loss": "▼", "Breakeven": "■"}

# Evidence chips are derived from the saved SMC flag columns (schema read-only).
_EVIDENCE_FLAGS = [
    ("liquidity_sweep", "Liquidity Sweep"),
    ("bos", "BOS"),
    ("choch", "MSS/CHOCH"),
    ("fvg_used", "FVG"),
    ("order_block_used", "OB Retest"),
]

_FILTER_KEYS = ("jf_from", "jf_to", "jf_assets", "jf_session", "jf_result", "jf_setup")


def _fmt_money(value) -> str:
    if value is None:
        return "—"
    return f"-${abs(value):,.2f}" if value < 0 else f"${value:,.2f}"


def _result_badge_html(result) -> str:
    label = humanize(result) if result else "—"
    variant = _RESULT_VARIANT.get(str(result or "").lower(), "neutral")
    return render_badge(label, variant)


def _clear_filters() -> None:
    """on_click callback — runs before widgets instantiate on the next run."""
    for key in _FILTER_KEYS:
        st.session_state.pop(key, None)


def _active_filters(
    *,
    date_from,
    date_to,
    assets,
    session,
    result,
    setup,
    default_from,
    default_to,
) -> list:
    """Only the filters actually narrowing the view, as (label, value) pairs.

    Defaults are omitted deliberately: a summary that lists every control at
    its default value states nothing and reads as clutter above the data it
    is meant to qualify.
    """
    pairs = []
    if str(date_from) != str(default_from) or str(date_to) != str(default_to):
        pairs.append(("Dates", f"{date_from} → {date_to}"))
    if assets:
        pairs.append(("Asset", ", ".join(str(a) for a in assets)))
    for label, value in (("Session", session), ("Result", result), ("Setup", setup)):
        if value and value != "All":
            pairs.append((label, str(value)))
    return pairs


def _result_count_html(shown: int, total: int) -> str:
    """The count, next to the view selector.

    States the filtered figure against the total so a trader can tell an
    empty result from an empty journal without scrolling.
    """
    noun = "trade" if shown == 1 else "trades"
    suffix = "" if shown == total else f" of {total}"
    return f'<p class="tl-journal-count">{shown}{suffix} {noun}</p>'


# The rule itself moved to components/ledger.py so it can be tested without
# booting this page; the name is kept here because the styler call reads
# better with it and nothing else needs to change.
_ledger_styles = ledger_row_styles


def _sanitize_multiselect(key: str, options: list) -> None:
    """Drop stale selections that fell out of the option set (date change)."""
    stale = st.session_state.get(key)
    if stale:
        st.session_state[key] = [v for v in stale if v in options]


def _sanitize_selectbox(key: str, options: list) -> None:
    if st.session_state.get(key) not in options:
        st.session_state.pop(key, None)


st.markdown(
    render_workspace_header(
        "Journal",
        "Find a trade, work a month, or read one closely.",
    ),
    unsafe_allow_html=True,
)

# ── Filters — one compact bar, secondary controls disclosed ───────
today = datetime.date.today()
_DEFAULT_FROM = today - datetime.timedelta(days=90)
_DEFAULT_TO = today

d1, d2, d3 = st.columns([1, 1, 2])
with d1:
    start_date = st.date_input("From", value=_DEFAULT_FROM, key="jf_from")
with d2:
    end_date = st.date_input("To", value=_DEFAULT_TO, key="jf_to")

# One fetch per run: server-side date + user scope, page-side facets.
trades_all = get_trades(
    start_date=str(start_date),
    end_date=str(end_date),
    user_id=uid,
)
asset_opts = sorted({t.asset for t in trades_all if t.asset})
setup_opts = ["All"] + sorted({t.setup_type for t in trades_all if t.setup_type})
session_opts = ["All"] + sorted({t.session for t in trades_all if t.session})

with d3:
    _sanitize_multiselect("jf_assets", asset_opts)
    assets_sel = st.multiselect(
        "Asset", asset_opts, key="jf_assets", placeholder="All assets"
    )

# Session / result / setup are the ones a trader reaches for occasionally.
# Behind a disclosure they stop being a second page above the page, and the
# active-filter summary below keeps their state visible when collapsed.
with st.expander("More filters"):
    f1, f2, f3 = st.columns(3)
    with f1:
        _sanitize_selectbox("jf_session", session_opts)
        session_sel = st.selectbox("Session", session_opts, key="jf_session")
    with f2:
        result_sel = st.selectbox(
            "Result", ["All", "Win", "Loss", "Breakeven"], key="jf_result"
        )
    with f3:
        _sanitize_selectbox("jf_setup", setup_opts)
        setup_sel = st.selectbox("Setup", setup_opts, key="jf_setup")
    st.button(
        "Clear filters",
        on_click=_clear_filters,
        key="secondary_jf_clear",
    )

trades = [
    t
    for t in trades_all
    if (not assets_sel or t.asset in assets_sel)
    and (session_sel == "All" or t.session == session_sel)
    and (result_sel == "All" or (t.result or "") == result_sel)
    and (setup_sel == "All" or (t.setup_type or "") == setup_sel)
]

# Demo banner when sample trades are present.
if any(getattr(t, "is_sample", 0) for t in trades):
    st.markdown(
        render_banner("Demo data is active. These are sample trades.", "info"),
        unsafe_allow_html=True,
    )

# ── Empty states ──────────────────────────────────────────────────
if not trades:
    if not trades_all and is_demo():
        ddf = get_demo_df()
        st.caption("Showing demo data (no trades logged yet).")
        # Named the way the real ledger names them. Measured in the browser:
        # this table was the one surface still exposing raw column names —
        # `trade_date`, `setup_type`, `killzone`, `pnl` — to sighted readers
        # and, through the grid's ARIA table, to screen readers. The ledger
        # below already reads Date / Asset / Setup / Session / Result / P&L,
        # and a trader meeting the product on an empty journal should not be
        # shown the schema.
        _DEMO_COLUMNS = {
            "trade_date": "Date",
            "asset": "Asset",
            "direction": "Direction",
            "setup_type": "Setup",
            "killzone": "Session",
            "result": "Result",
            "pnl": "P&L",
        }
        ddf = ddf[list(_DEMO_COLUMNS)].rename(columns=_DEMO_COLUMNS)
        st.dataframe(ddf, hide_index=True, width="stretch")
        st.stop()
    if trades_all:
        st.markdown(
            render_empty_state(
                "",
                "No trades match your filters",
                "Adjust or clear the filters above to see more of your journal.",
            ),
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            render_empty_state(
                "",
                "No trades yet",
                "Log your first trade to start building your journal.",
                image_path="empty_trades.png",
            ),
            unsafe_allow_html=True,
        )
        c1, c2 = st.columns(2)
        # page_link needs the multipage registry, which standalone AppTest
        # boots don't build — degrade to a plain slug link (sidebar pattern).
        for col, page, slug, label in (
            (c1, "pages/1_NewTrade.py", "/NewTrade", "Log your first trade →"),
            (c2, "pages/9_Settings.py", "/Settings", "Load sample trades →"),
        ):
            try:
                col.page_link(page, label=label)
            except Exception:  # noqa: BLE001 — registry-less boots/tests only
                col.markdown(
                    f'<a href="{slug}" target="_self">{label}</a>',
                    unsafe_allow_html=True,
                )
    st.stop()

# ── Build the table ───────────────────────────────────────────────
ids = []
labels = {}
rows = []
for t in trades:
    ids.append(t.id)
    labels[t.id] = f"#{t.id} · {t.trade_date or '—'} · {t.asset} · {t.result or '?'}"
    _result = humanize(t.result) if t.result else "—"
    rows.append(
        {
            # Spec 11.3's scannable set. Killzone and Direction moved to Trade
            # Detail: they are read once, when studying a trade, not scanned.
            "Date": t.trade_date or "—",
            "Asset": t.asset or "—",
            "Session": humanize(t.session),
            "Setup": humanize(t.setup_type),
            # The glyph is the semantic edge — the result stays legible with
            # no colour at all.
            "Result": f"{_LEDGER_MARKS.get(_result, '·')} {_result}",
            "P&L": _fmt_money(t.pnl),
            "R": f"{t.rr_realized:.2f}R" if t.rr_realized is not None else "—",
            "Grade": t.user_grade or t.ai_grade or "—",
            "Shot": "Yes" if t.screenshots else "",
        }
    )

df = pd.DataFrame(rows)

# ── Active filters + view selector ────────────────────────────────
_filters = _active_filters(
    date_from=start_date,
    date_to=end_date,
    assets=assets_sel,
    session=session_sel,
    result=result_sel,
    setup=setup_sel,
    default_from=_DEFAULT_FROM,
    default_to=_DEFAULT_TO,
)
st.markdown(render_filter_summary(_filters), unsafe_allow_html=True)

# Apply any pending view change BEFORE the selector is instantiated. After
# that point Streamlit treats the selector's key as owned by the widget and
# raises on any write to it.
_goto = st.session_state.pop(_GOTO_KEY, None)
if _goto in JOURNAL_VIEWS:
    st.session_state[_VIEW_KEY] = _goto
    # Drop the widget's own state so it re-initialises from the new default.
    st.session_state.pop(_VIEW_WIDGET_KEY, None)

_default_view = st.session_state.get(_VIEW_KEY, JOURNAL_VIEWS[0])
if _default_view not in JOURNAL_VIEWS:
    _default_view = JOURNAL_VIEWS[0]

_view_col, _count_col = st.columns([2, 1], vertical_alignment="center")
with _view_col:
    # A radio group, not st.segmented_control: three mutually exclusive
    # views ARE a radio group semantically (one role, arrow-key navigation,
    # announced as "1 of 3"), and st.segmented_control cannot be driven
    # under AppTest on the pinned Streamlit — it raises on state
    # serialisation, which would leave this page's primary navigation with
    # no automated coverage at all.
    _picked_view = st.radio(
        "Journal view",
        JOURNAL_VIEWS,
        index=JOURNAL_VIEWS.index(_default_view),
        horizontal=True,
        key=_VIEW_WIDGET_KEY,
        label_visibility="collapsed",
    )
view = _picked_view or _default_view
# _VIEW_KEY is a plain key, not the widget's — safe to write at any point.
st.session_state[_VIEW_KEY] = view
_count_col.markdown(
    _result_count_html(len(trades), len(trades_all)), unsafe_allow_html=True
)


def _open_trade(trade_id: int) -> None:
    """Selecting a trade moves the trader to the focused view.

    Records an intent rather than setting the selector directly: this runs
    below the selector, and writing a widget's key after instantiation is a
    StreamlitAPIException.
    """
    st.session_state["selected_trade_id"] = trade_id
    st.session_state[_GOTO_KEY] = "Trade Detail"


# ══════════════════════════════════════════════════════════════════
# View — Trades ledger
# ══════════════════════════════════════════════════════════════════
if view == "Trades":
    event = st.dataframe(
        df.style.apply(_ledger_styles, axis=1),
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="single-row",
        key="journal_table",
    )

    selected_rows = []
    try:
        selected_rows = event.selection["rows"]
    except Exception:  # noqa: BLE001 — older/edge AppTest selection shapes
        selected_rows = []
    if selected_rows:
        _open_trade(ids[selected_rows[0]])
        st.rerun()

    picked = st.selectbox(
        "Open a trade",
        [None] + ids,
        format_func=lambda i: "—" if i is None else labels.get(i, str(i)),
        key="journal_pick",
        help="Or click a row above.",
    )
    if picked is not None and picked != st.session_state.get("selected_trade_id"):
        _open_trade(picked)
        st.rerun()

# ══════════════════════════════════════════════════════════════════
# View — Calendar (the full interactive month; Overview owns the preview)
# ══════════════════════════════════════════════════════════════════
if view == "Calendar":
    # `id` travels with the calendar data so a selected day can offer real
    # openers. Overview and Analytics build their own frames and are
    # unaffected; the calendar itself only ever reads the columns it needs.
    _cal_df = pd.DataFrame(
        [
            {
                "id": t.id,
                "trade_date": t.trade_date,
                "pnl": t.pnl,
                "asset": t.asset,
                "direction": t.direction,
                "setup_type": t.setup_type,
                "result": t.result,
            }
            for t in trades
        ]
    )
    # Keyed so the design system can keep this month a real 7-across grid at
    # phone widths. The key names the calendar form, not this page: Analytics
    # mounts the same component and needs the same rule. Overview's preview is
    # its own CSS grid and is unaffected.
    with st.container(key="tl_full_calendar"):
        _day = render_trade_calendar(_cal_df)
    if _day:
        _day_trades = [t for t in trades if str(t.trade_date) == str(_day)]
        if _day_trades:
            st.markdown(
                render_section_header(f"Open a trade from {_day}"),
                unsafe_allow_html=True,
            )
            # Buttons, not links: they are focusable and activate on Enter or
            # Space, so a day's trades are reachable without a mouse. Each
            # routes through the same intent mechanism as a ledger row, so the
            # widget-state crash cannot come back through this path.
            for _t in _day_trades:
                st.button(
                    f"{_t.asset or '—'} · {humanize(_t.result) or '—'} · "
                    f"{_fmt_money(_t.pnl)}",
                    key=f"journal_calopen_{_t.id}",
                    on_click=_open_trade,
                    args=(_t.id,),
                    width="stretch",
                )

# ── AI summary of the filtered trades (multi-trade reflection) ────
if view == "Trades" and len(trades) >= 2:
    with st.expander(f"AI summary of these {len(trades)} trades"):
        st.caption(
            "Patterns across the trades matching your filters — recurring "
            "mistakes, setup quality, emotions, and rule adherence. Post-trade "
            "reflection only, never signals."
        )
        if not ai_available():
            st.info(
                "AI features are off. Add your Anthropic API key in Settings "
                "to enable them."
            )
        else:
            _sum_sig = (
                uid,
                str(start_date),
                str(end_date),
                tuple(assets_sel),
                session_sel,
                result_sel,
                setup_sel,
                len(trades),
            )
            _cached = st.session_state.get("_trades_summary") or {}
            _is_current = _cached.get("sig") == _sum_sig
            if _is_current:
                # The generated prose keeps the shared evidence treatment, but
                # it is a five-section Markdown document — headings, bold, and
                # lists. Passing it as a readout BODY escapes every one of
                # those into literal ###, ** and - characters.
                #
                # So it is rendered by Streamlit's own Markdown renderer with
                # unsafe HTML OFF: model output must never reach an
                # HTML-allowing path. The Evidence Rail is our own markup with
                # escaped values, so it is emitted separately.
                #
                # What the call cost is operator accounting, not something a
                # trader needs while reading a review — see Settings.
                _capped = min(len(trades), 40)
                st.markdown(
                    render_section_header("Across the trades in this filter"),
                    unsafe_allow_html=True,
                )
                st.markdown(_cached["review"].get("content_md") or "")
                st.markdown(
                    render_evidence_rail(
                        EvidenceItem(
                            evidence="Trades matching the current Journal filters",
                            sample=f"n={_capped} · {start_date} → {end_date}",
                            confidence=(
                                "high"
                                if _capped >= 20
                                else "medium" if _capped >= 8 else "low"
                            ),
                            limitation=(
                                "Only the newest 40 trades of this selection "
                                "were reviewed."
                                if len(trades) > 40
                                else None
                            ),
                        )
                    ),
                    unsafe_allow_html=True,
                )
            if len(trades) > 40:
                st.caption("Large selection — the newest 40 trades are included.")
            _sum_label = (
                "Regenerate summary"
                if _is_current
                else f"Summarize these {len(trades)} trades"
            )
            if st.button(_sum_label, key="journal_sum_btn"):
                with st.spinner("Reviewing these trades with AI…"):
                    try:
                        _review, _usage = generate_debrief(
                            trades,
                            strategy_profile=_strategy_profile,
                            period_label=(
                                f"Selected trades {start_date} → {end_date} "
                                f"({len(trades)} trades matching the current "
                                "Journal filters)"
                            ),
                        )
                        log_ai_usage("Trade Summary", _usage, user_id=uid)
                        st.session_state["_trades_summary"] = {
                            "sig": _sum_sig,
                            "review": _review,
                        }
                        st.rerun()
                    except DebriefError:
                        st.warning(
                            "The AI summary didn't finish. Try again in a moment."
                        )
                    except Exception:  # noqa: BLE001 — never crash the Journal
                        st.warning("The AI summary didn't finish. Try again.")

selected_id = st.session_state.get("selected_trade_id")
if selected_id not in ids:
    selected_id = None


# ── Detail helpers ────────────────────────────────────────────────
def _detail_header_html(trade) -> str:
    pnl = trade.pnl
    if pnl is None:
        pnl_color = "var(--tl-content-secondary)"
    elif pnl > 0:
        pnl_color = "var(--tl-success)"
    elif pnl < 0:
        pnl_color = "var(--tl-danger)"
    else:
        pnl_color = "var(--tl-content-primary)"
    chips = render_badge(humanize(trade.session) or "—", "neutral")
    chips += _result_badge_html(trade.result)
    return (
        '<div class="tl-form-card" style="display:flex;align-items:center;'
        'justify-content:space-between;gap:16px;flex-wrap:wrap">'
        "<div>"
        f'<h3 style="margin:0 0 6px 0">'
        f"{escape(trade.asset or '—')} · {escape(trade.trade_date or '—')}</h3>"
        f'<div class="tl-chip-row">{chips}</div>'
        "</div>"
        f'<div style="font-family:var(--tl-font-mono);font-size:30px;'
        f'font-weight:600;color:{pnl_color}">{escape(_fmt_money(pnl))}</div>'
        "</div>"
    )


def _price_grid_html(trade) -> str:
    def row(label: str, value) -> str:
        shown = (
            f"<span style='font-family:var(--tl-font-mono)'>{escape(str(value))}"
            "</span>"
            if value is not None
            else "<span style='color:var(--tl-content-secondary)'>—</span>"
        )
        return (
            '<div style="display:flex;justify-content:space-between;'
            'gap:16px;padding:3px 0">'
            f'<span style="color:var(--tl-content-secondary)">{escape(label)}</span>'
            f"{shown}</div>"
        )

    rr_p = f"{trade.rr_planned:.2f}R" if trade.rr_planned is not None else None
    rr_r = f"{trade.rr_realized:.2f}R" if trade.rr_realized is not None else None
    body = "".join(
        row(label, value)
        for label, value in [
            ("Entry", trade.entry_price),
            ("Stop", trade.stop_price),
            ("Take Profit", trade.tp_price),
            ("Exit", trade.exit_price),
            ("Planned R", rr_p),
            ("Realized R", rr_r),
        ]
    )
    return f'<div class="tl-form-card">{body}</div>'


def _split_notes(notes: str):
    """Pull the structured review lines back out of the notes column."""
    did = improve = rule = None
    rest = []
    for line in (notes or "").splitlines():
        s = line.strip()
        low = s.lower()
        if low.startswith("did well:"):
            did = s[len("did well:") :].strip()
        elif low.startswith("do better next time:"):
            improve = s[len("do better next time:") :].strip()
        elif low.startswith("rule broken:"):
            rule = s[len("rule broken:") :].strip()
        elif s:
            rest.append(s)
    return did, improve, rule, ("\n".join(rest) or None)


def _evidence_chips(trade) -> list:
    return [label for attr, label in _EVIDENCE_FLAGS if getattr(trade, attr, None)]


def _mistake_chips(trade) -> list:
    try:
        tags = json.loads(trade.mistake_tags or "[]")
    except (json.JSONDecodeError, TypeError):
        tags = []
    return [str(tag) for tag in tags if tag]


def _render_screenshot(file_path) -> bool:
    """Render a screenshot from a URL or a local path. Returns True if shown."""
    if not file_path:
        return False
    path = str(file_path)
    if path.startswith("http"):
        st.image(path, width=460)
        return True
    if Path(path).exists():
        st.image(path, width=460)
        return True
    return False


# ══════════════════════════════════════════════════════════════════
# View — Trade Detail
# ══════════════════════════════════════════════════════════════════
if view == "Trade Detail":
    if selected_id is None:
        st.markdown(
            render_empty_state(
                "",
                "No trade selected",
                "Pick a trade from the Trades ledger or the Calendar to read it here.",
            ),
            unsafe_allow_html=True,
        )
        st.stop()

    trade = get_trade(selected_id, user_id=uid)
    if trade is None:
        st.stop()

    # A predictable back path. Selecting a row is a one-way door without it.
    def _back_to_trades() -> None:
        st.session_state[_GOTO_KEY] = "Trades"

    st.button(
        "← Back to trades", key="secondary_journal_back", on_click=_back_to_trades
    )

    # The one animation on this page. Opening a trade is a real change of
    # context, so a brief reveal explains where the content came from. The
    # ledger itself stays instant: rows are scanned dozens of times a
    # session, and anything that takes time there reads as lag.
    _detail_panel = st.container(key="tl_trade_detail")
    with _detail_panel:
        st.markdown(_detail_header_html(trade), unsafe_allow_html=True)

    left, right = st.columns([5, 7], gap="large")

    with left:
        st.markdown("**Chart Screenshot**")
        shots = sorted(
            trade.screenshots or [], key=lambda s: s.uploaded_at or "", reverse=True
        )
        shown = _render_screenshot(shots[0].file_path) if shots else False
        if not shown:
            st.caption("No screenshot attached to this trade.")
            up = st.file_uploader(
                "Add screenshot", type=["png", "jpg", "jpeg", "webp"], key="detail_shot"
            )
            if up is not None:
                save_screenshot(trade.id, up)
                st.toast("Screenshot added", icon=":material/check_circle:")
                st.rerun()
        render_screenshot_analyzer(
            trade, user_id=uid, strategy_profile=_strategy_profile
        )

    _did, _improve, _rule, _extra_notes = _split_notes(trade.notes)

    with right:
        st.markdown("**Setup**")
        setup_chips = render_badge(humanize(trade.setup_type) or "—", "primary")
        evidence = _evidence_chips(trade)
        if evidence:
            setup_chips += render_chip_row(evidence)
        if trade.followed_rules is not None:
            rules_variant = "success" if trade.followed_rules else "danger"
            rules_label = "Followed rules" if trade.followed_rules else "Broke a rule"
            setup_chips += render_badge(rules_label, rules_variant)
        st.markdown(
            f'<div class="tl-chip-row">{setup_chips}</div>', unsafe_allow_html=True
        )
        detail_bits = [
            f"Direction: {humanize(trade.direction)}",
            f"Killzone: {humanize(trade.killzone)}",
            f"HTF Bias: {humanize(trade.htf_bias)}",
        ]
        if trade.confirmation_model:
            detail_bits.append(f"Confirmed by: {trade.confirmation_model}")
        st.caption("  ·  ".join(detail_bits))
        if _rule:
            st.caption(f"Rule broken: {_rule}")
        if trade.strategy_used:
            st.caption(f"Strategy: {trade.strategy_used}")

        st.markdown("**Risk & Outcome**")
        st.markdown(_price_grid_html(trade), unsafe_allow_html=True)

        st.markdown("**Psychology**")
        if trade.trade_process_notes:
            st.markdown(f"*What happened:* {trade.trade_process_notes}")
        if _did:
            st.markdown(f"*Did well:* {_did}")
        if _improve:
            st.markdown(f"*Improve:* {_improve}")
        mistakes = _mistake_chips(trade)
        if mistakes:
            st.markdown(
                render_chip_row(mistakes, {m: "danger" for m in mistakes}),
                unsafe_allow_html=True,
            )
        emo = "  ·  ".join(
            f"{lbl}: {humanize(val)}"
            for lbl, val in (
                ("Before", trade.emotions_before),
                ("During", trade.emotions_during),
                ("After", trade.emotions_after),
            )
            if val
        )
        if emo:
            st.caption(emo)
        if _extra_notes:
            st.markdown("**Notes**")
            st.markdown(_extra_notes)

    # ── Quick actions ─────────────────────────────────────────────
    with st.expander("Edit Trade"):
        e1, e2 = st.columns(2)
        with e1:
            new_result = st.selectbox(
                "Result",
                ["Win", "Loss", "Breakeven"],
                index=(
                    ["Win", "Loss", "Breakeven"].index(trade.result)
                    if trade.result in ("Win", "Loss", "Breakeven")
                    else 0
                ),
                key="edit_result",
            )
            new_pnl = st.number_input(
                "P&L ($)",
                value=float(trade.pnl) if trade.pnl is not None else None,
                key="edit_pnl",
            )
        with e2:
            grade_opts = ["—", "A", "B", "C", "D", "F"]
            cur_grade = trade.user_grade if trade.user_grade in grade_opts else "—"
            new_grade = st.selectbox(
                "Your Grade",
                grade_opts,
                index=grade_opts.index(cur_grade),
                key="edit_grade",
            )
        new_notes = st.text_area("Notes", value=trade.notes or "", key="edit_notes")
        if st.button("Save changes", type="primary", key="edit_save"):
            try:
                update_trade(
                    trade.id,
                    user_id=uid,
                    result=new_result,
                    pnl=new_pnl,
                    user_grade=None if new_grade == "—" else new_grade,
                    notes=new_notes.strip() or None,
                )
            except OutcomeMismatch as exc:
                # Stays on screen next to the fields that disagree — a toast
                # would vanish before the trader could correct either one.
                st.markdown(render_banner(str(exc), "danger"), unsafe_allow_html=True)
            else:
                st.toast("Trade updated", icon=":material/check_circle:")
                st.rerun()

    with st.expander("Delete trade"):
        st.warning("Deleting this trade can't be undone.")
        confirm = st.checkbox("I'm sure", key="delete_confirm")
        if st.button("Delete trade", disabled=not confirm, key="secondary_delete_btn"):
            if delete_trade(trade.id, user_id=uid):
                st.session_state.pop("selected_trade_id", None)
                st.toast("Trade deleted", icon=":material/check_circle:")
                st.rerun()
            st.stop()

    # ── AI Review (journal + process grade) ───────────────────────
    render_ai_review(trade, _strategy_profile, user_id=uid)

    # ── Ask AI About This Trade ───────────────────────────────────
    render_ask_ai(trade, _strategy_profile)
