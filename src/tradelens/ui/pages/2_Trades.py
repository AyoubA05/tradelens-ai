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
from src.tradelens.ui.components.ai_review import render_ai_review  # noqa: E402
from src.tradelens.ui.components.auth import current_user_id, require_auth  # noqa: E402
from src.tradelens.ui.components.ai_trade_chat import render_ask_ai  # noqa: E402
from src.tradelens.ui.components.corrections_sidebar import (  # noqa: E402
    render_corrections_sidebar,
)
from src.tradelens.ui.components.demo_banner import render_demo_banner  # noqa: E402
from src.tradelens.ui.components.screenshot_analyzer import (  # noqa: E402
    render_screenshot_analyzer,
)
from src.tradelens.ui.components.sidebar import render_sidebar  # noqa: E402
from src.tradelens.ui.components.theme import inject_css  # noqa: E402
from src.tradelens.ui.design_system import (  # noqa: E402
    TL_DANGER,
    TL_DANGER_DIM,
    TL_SUCCESS,
    TL_SUCCESS_DIM,
    inject_design_system,
    render_badge,
    render_banner,
    render_chip_row,
    render_empty_state,
    render_section_header,
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
st.markdown(
    render_section_header("Journal", "Review, filter, and reflect on your trades"),
    unsafe_allow_html=True,
)

_RESULT_VARIANT = {"win": "success", "loss": "danger", "breakeven": "neutral"}

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


def _sanitize_multiselect(key: str, options: list) -> None:
    """Drop stale selections that fell out of the option set (date change)."""
    stale = st.session_state.get(key)
    if stale:
        st.session_state[key] = [v for v in stale if v in options]


def _sanitize_selectbox(key: str, options: list) -> None:
    if st.session_state.get(key) not in options:
        st.session_state.pop(key, None)


# ── Filters ───────────────────────────────────────────────────────
with st.container(border=True):
    today = datetime.date.today()
    d1, d2, d3 = st.columns([1, 1, 2])
    with d1:
        start_date = st.date_input(
            "From", value=today - datetime.timedelta(days=90), key="jf_from"
        )
    with d2:
        end_date = st.date_input("To", value=today, key="jf_to")

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

    f1, f2, f3, f4 = st.columns([1, 1, 1, 1])
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
    with f4:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        st.button(
            "Clear Filters",
            on_click=_clear_filters,
            width="stretch",
            key="jf_clear",
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
        ddf = ddf[
            [
                "trade_date",
                "asset",
                "direction",
                "setup_type",
                "killzone",
                "result",
                "pnl",
            ]
        ]
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
    rows.append(
        {
            "Date": t.trade_date or "—",
            "Killzone": humanize(t.killzone),
            "Asset": t.asset or "—",
            "Session": humanize(t.session),
            "Setup": humanize(t.setup_type),
            "Direction": humanize(t.direction),
            "Result": humanize(t.result) if t.result else "—",
            "P&L": _fmt_money(t.pnl),
            "R": f"{t.rr_realized:.2f}R" if t.rr_realized is not None else "—",
            "Grade": t.user_grade or t.ai_grade or "—",
            "📷": "📷" if t.screenshots else "",
        }
    )

df = pd.DataFrame(rows)


def _row_style(row):
    """Result tint on the row; sign color on the P&L and R cells."""
    if row["Result"] == "Win":
        base = f"background-color: {TL_SUCCESS_DIM}"
    elif row["Result"] == "Loss":
        base = f"background-color: {TL_DANGER_DIM}"
    else:
        base = ""
    styles = [base] * len(row)
    for col in ("P&L", "R"):
        i = row.index.get_loc(col)
        val = row[col]
        if val.startswith("-"):
            color = f"color: {TL_DANGER}"
        elif val not in ("—", "$0.00", "0.00R"):
            color = f"color: {TL_SUCCESS}"
        else:
            color = ""
        styles[i] = f"{base}; {color}".strip("; ")
    return styles


st.markdown(
    render_badge(f"{len(trades)} trades", "neutral"),
    unsafe_allow_html=True,
)
event = st.dataframe(
    df.style.apply(_row_style, axis=1),
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
    st.session_state["selected_trade_id"] = ids[selected_rows[0]]

with st.expander("Or pick a trade from a list"):
    picked = st.selectbox(
        "Trade",
        [None] + ids,
        format_func=lambda i: "—" if i is None else labels.get(i, str(i)),
        key="journal_pick",
    )
    if picked is not None:
        st.session_state["selected_trade_id"] = picked

# ── AI summary of the filtered trades (multi-trade reflection) ────
if len(trades) >= 2:
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
                st.markdown(_cached["review"].get("content_md") or "")
                _cost = _cached["review"].get("cost_usd")
                if _cost:
                    st.caption(f"Generation cost: ${_cost:.4f}")
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
        pnl_color = "var(--tl-text-muted)"
    elif pnl > 0:
        pnl_color = "var(--tl-success)"
    elif pnl < 0:
        pnl_color = "var(--tl-danger)"
    else:
        pnl_color = "var(--tl-text)"
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
            else "<span style='color:var(--tl-text-muted)'>—</span>"
        )
        return (
            '<div style="display:flex;justify-content:space-between;'
            'gap:16px;padding:3px 0">'
            f'<span style="color:var(--tl-text-muted)">{escape(label)}</span>'
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


# ── Trade detail panel ────────────────────────────────────────────
if selected_id is not None:
    trade = get_trade(selected_id, user_id=uid)
    if trade is None:
        st.stop()

    st.divider()
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
                st.toast("Screenshot added", icon="✅")
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
            update_trade(
                trade.id,
                user_id=uid,
                result=new_result,
                pnl=new_pnl,
                user_grade=None if new_grade == "—" else new_grade,
                notes=new_notes.strip() or None,
            )
            st.toast("Trade updated", icon="✅")
            st.rerun()

    with st.expander("Delete trade"):
        st.warning("Deleting this trade can't be undone.")
        confirm = st.checkbox("I'm sure", key="delete_confirm")
        if st.button("Delete trade", disabled=not confirm, key="delete_btn"):
            if delete_trade(trade.id, user_id=uid):
                st.session_state.pop("selected_trade_id", None)
                st.toast("Trade deleted", icon="✅")
                st.rerun()
            st.stop()

    # ── AI Review (journal + process grade) ───────────────────────
    render_ai_review(trade, _strategy_profile, user_id=uid)

    # ── Ask AI About This Trade ───────────────────────────────────
    render_ask_ai(trade, _strategy_profile)
