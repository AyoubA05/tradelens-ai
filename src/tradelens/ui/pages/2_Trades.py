import sys
from pathlib import Path

# parents[4] of src/tradelens/ui/pages/2_Trades.py  →  project root
_root = str(Path(__file__).resolve().parents[4])
if _root not in sys.path:
    sys.path.insert(0, _root)

import datetime  # noqa: E402

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src.tradelens.services.demo import get_demo_df, is_demo  # noqa: E402
from src.tradelens.services.screenshot_service import save_screenshot  # noqa: E402
from src.tradelens.services.strategy import get_active_strategy  # noqa: E402
from src.tradelens.services.trade_service import (  # noqa: E402
    delete_trade,
    get_trade,
    get_trades,
    update_trade,
)
from src.tradelens.ui.components.auth import current_user_id, require_auth  # noqa: E402
from src.tradelens.ui.components.ai_trade_chat import render_ask_ai  # noqa: E402
from src.tradelens.ui.components.demo_banner import render_demo_banner  # noqa: E402
from src.tradelens.ui.components.screenshot_analyzer import (  # noqa: E402
    render_screenshot_analyzer,
)
from src.tradelens.ui.components.sidebar import render_sidebar  # noqa: E402
from src.tradelens.ui.components.theme import inject_css  # noqa: E402
from src.tradelens.ui.components.ui import empty_state, section_header  # noqa: E402
from src.tradelens.utils.format import humanize  # noqa: E402

st.set_page_config(page_title="Journal", layout="wide")
inject_css()
require_auth()
render_demo_banner()
render_sidebar()
st.markdown(
    section_header("Journal", "Review, filter, and reflect on your trades"),
    unsafe_allow_html=True,
)


def _fmt_money(value) -> str:
    if value is None:
        return "—"
    return f"-${abs(value):,.2f}" if value < 0 else f"${value:,.2f}"


def _result_badge(result) -> str:
    return {
        "win": "🟢 Win",
        "loss": "🔴 Loss",
        "breakeven": "⚪ Breakeven",
    }.get(str(result or "").lower(), "—")


def _render_screenshot(file_path) -> bool:
    """Render a screenshot from a URL or a local path. Returns True if shown."""
    if not file_path:
        return False
    path = str(file_path)
    if path.startswith("http"):
        st.image(path, use_container_width=True)
        return True
    if Path(path).exists():
        st.image(path, use_container_width=True)
        return True
    return False


# ── Filters ───────────────────────────────────────────────────────
f1, f2, f3, f4 = st.columns(4)
with f1:
    today = datetime.date.today()
    start_date = st.date_input("From", value=today - datetime.timedelta(days=90))
    end_date = st.date_input("To", value=today)
with f2:
    asset_filter = st.text_input("Asset", placeholder="All")
with f3:
    direction_filter = st.selectbox("Direction", ["All", "Long", "Short"])
with f4:
    result_filter = st.selectbox("Result", ["All", "Win", "Loss", "Breakeven"])

trades = get_trades(
    start_date=str(start_date),
    end_date=str(end_date),
    asset=asset_filter or None,
    result=result_filter,
    user_id=current_user_id(),
)
if direction_filter != "All":
    trades = [t for t in trades if (t.direction or "") == direction_filter]

# Demo banner when sample trades are present.
if any(getattr(t, "is_sample", 0) for t in trades):
    st.info("🔬 Demo data is active. These are sample trades.")

# ── Empty states ──────────────────────────────────────────────────
if not trades:
    using_filters = (
        bool(asset_filter) or direction_filter != "All" or result_filter != "All"
    )
    if is_demo():
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
        st.dataframe(ddf, hide_index=True, use_container_width=True)
        st.stop()
    if using_filters:
        st.markdown(
            empty_state("No trades match your filters."),
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            empty_state(
                "No trades yet. Log your first trade.",
                cta_label="Log Trade",
                cta_href="/NewTrade",
            ),
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
            "Asset": t.asset or "—",
            "Direction": humanize(t.direction),
            "Setup": humanize(t.setup_type),
            "Killzone": humanize(t.killzone),
            "Result": _result_badge(t.result),
            "P&L": _fmt_money(t.pnl),
            "R": f"{t.rr_realized:.2f}R" if t.rr_realized is not None else "—",
            "Grade": t.user_grade or t.ai_grade or "—",
            "Screenshot": "📷" if t.screenshots else "—",
            "Notes": ((t.notes or "")[:50] or "—"),
        }
    )

df = pd.DataFrame(rows)


def _tint(row):
    label = row["Result"]
    if "Win" in label:
        color = "background-color: rgba(32,128,141,0.10)"
    elif "Loss" in label:
        color = "background-color: rgba(168,75,47,0.10)"
    else:
        color = ""
    return [color] * len(row)


st.caption(f"{len(trades)} trades")
event = st.dataframe(
    df.style.apply(_tint, axis=1),
    hide_index=True,
    use_container_width=True,
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
    st.session_state["journal_selected_id"] = ids[selected_rows[0]]

with st.expander("Or pick a trade from a list"):
    picked = st.selectbox(
        "Trade",
        [None] + ids,
        format_func=lambda i: "—" if i is None else labels.get(i, str(i)),
        key="journal_pick",
    )
    if picked is not None:
        st.session_state["journal_selected_id"] = picked

selected_id = st.session_state.get("journal_selected_id")
if selected_id not in ids:
    selected_id = None

# ── Trade detail panel ────────────────────────────────────────────
if selected_id is not None:
    trade = get_trade(selected_id)
    if trade is None:
        st.stop()

    st.divider()
    st.markdown(
        section_header(f"Trade #{trade.id} — {trade.asset}"), unsafe_allow_html=True
    )

    left, right = st.columns([5, 7], gap="large")

    with left:
        st.markdown("**Setup**")
        st.markdown(
            f"- Date: {trade.trade_date or '—'}  ·  Direction: {humanize(trade.direction)}\n"
            f"- Setup: {humanize(trade.setup_type)}  ·  Killzone: {humanize(trade.killzone)}\n"
            f"- Confirmation: {humanize(trade.confirmation_model)}\n"
            f"- HTF Bias: {humanize(trade.htf_bias)}  ·  Session: {humanize(trade.session)}"
        )
        st.markdown("**Risk & Outcome**")
        rr = f"{trade.rr_realized:.2f}R" if trade.rr_realized is not None else "—"
        st.markdown(
            f"- Result: {_result_badge(trade.result)}  ·  P&L: {_fmt_money(trade.pnl)}\n"
            f"- Realized R: {rr}  ·  Entry: {trade.entry_price or '—'}  ·  "
            f"Stop: {trade.stop_price or '—'}  ·  Exit: {trade.exit_price or '—'}"
        )
        if trade.strategy_used:
            st.caption(f"Strategy: {trade.strategy_used}")
        st.markdown("**Psychology**")
        emo = "  ·  ".join(
            f"{lbl}: {humanize(val)}"
            for lbl, val in (
                ("Before", trade.emotions_before),
                ("During", trade.emotions_during),
                ("After", trade.emotions_after),
            )
            if val
        )
        st.markdown(emo or "—")
        if trade.notes:
            st.markdown("**Notes**")
            st.markdown(trade.notes)

    with right:
        st.markdown("**Chart Screenshot**")
        shots = sorted(
            trade.screenshots or [], key=lambda s: s.uploaded_at or "", reverse=True
        )
        shown = _render_screenshot(shots[0].file_path) if shots else False
        if not shown:
            st.info("📷 No screenshot.")
            up = st.file_uploader(
                "Add screenshot", type=["png", "jpg", "jpeg", "webp"], key="detail_shot"
            )
            if up is not None:
                save_screenshot(trade.id, up)
                st.toast("Screenshot added", icon="✓")
                st.rerun()

        render_screenshot_analyzer(trade, get_active_strategy())

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
                result=new_result,
                pnl=new_pnl,
                user_grade=None if new_grade == "—" else new_grade,
                notes=new_notes.strip() or None,
            )
            st.toast("Trade updated", icon="✓")
            st.rerun()

    with st.expander("Delete Trade"):
        st.warning("This permanently deletes the trade.")
        confirm = st.checkbox("I'm sure", key="delete_confirm")
        if st.button("Delete Trade", disabled=not confirm, key="delete_btn"):
            delete_trade(trade.id)
            st.session_state.pop("journal_selected_id", None)
            st.toast("Trade deleted", icon="✓")
            st.rerun()

    # ── Ask AI About This Trade ───────────────────────────────────
    render_ask_ai(trade, get_active_strategy())
