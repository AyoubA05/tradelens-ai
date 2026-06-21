import sys
import datetime
from pathlib import Path

# parents[4] of src/tradelens/ui/pages/*.py  →  project root
_root = str(Path(__file__).resolve().parents[4])
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st  # noqa: E402

from src.tradelens.services.weekly import (  # noqa: E402
    WeeklyReviewError,
    generate_weekly_review,
    get_weekly_review,
    list_weekly_reviews,
    save_weekly_review,
    week_bounds,
)
from src.tradelens.ui.components.demo_banner import render_demo_banner  # noqa: E402
from src.tradelens.ui.components.theme import inject_css  # noqa: E402
from src.tradelens.ui.components.ui import empty_state, section_header  # noqa: E402

st.set_page_config(page_title="Weekly Review", layout="wide")
inject_css()
render_demo_banner()
st.markdown(
    section_header(
        "Weekly AI Review",
        "Post-trade reflection on a completed week — not signals or advice.",
    ),
    unsafe_allow_html=True,
)


def _fmt_pf(pf) -> str:
    if pf is None:
        return "∞"
    return f"{pf:.2f}"


def _render_stats_sidebar(stats: dict) -> None:
    with st.sidebar:
        st.header("Week Stats")
        if not stats:
            st.caption("Generate a review to see this week's stats.")
            return
        st.metric("Trades", stats.get("trades", 0))
        st.metric("Win Rate", f"{stats.get('win_rate', 0.0):.1%}")
        st.metric("Net P/L", f"${stats.get('total_pnl', 0.0):,.2f}")
        st.metric("Profit Factor", _fmt_pf(stats.get("profit_factor")))
        leak = stats.get("total_edge_leak", 0.0)
        st.metric("Edge Leak", f"${leak:,.2f}")


def _render_review(review: dict) -> None:
    if review.get("content_md"):
        st.markdown(review["content_md"])
    thinking = review.get("thinking_summary")
    if thinking:
        with st.expander("How the AI reasoned"):
            st.markdown(thinking)
    cost = review.get("cost_usd")
    if cost:
        st.caption(f"Generation cost: ${cost:.4f}")


# --- Week picker (any day → that Mon–Sun week) ---
today = datetime.date.today()
picked = st.date_input("Pick any day in the week to review", value=today)
monday, sunday = week_bounds(picked)
st.subheader(f"Week of {monday} → {sunday}")

existing = get_weekly_review(monday)
_render_stats_sidebar(existing["stats"] if existing else {})

# --- Generate / regenerate flow with overwrite confirmation ---
confirm_key = "wk_confirm_overwrite"

if existing is None:
    if st.button("Generate weekly review", type="primary"):
        with st.spinner("Writing weekly review with Fable 5…"):
            try:
                review, _usage = generate_weekly_review(monday)
                if review["empty"]:
                    st.markdown(
                        empty_state(
                            "This week has no trades to review yet.",
                            cta_label="Log a trade",
                            cta_href="/NewTrade",
                        ),
                        unsafe_allow_html=True,
                    )
                else:
                    save_weekly_review(review, overwrite=False)
                    st.toast("Weekly review generated", icon="✓")
                    st.rerun()
            except WeeklyReviewError as exc:
                st.toast(f"Could not generate review: {exc}", icon="✕")
            except Exception as exc:
                st.toast(f"Unexpected error: {exc}", icon="✕")
else:
    _render_review(existing)
    st.markdown("---")
    if st.session_state.get(confirm_key) == monday:
        st.warning(
            "Regenerating overwrites the saved review for this week and makes a "
            "new AI call. Continue?"
        )
        c1, c2 = st.columns(2)
        if c1.button("Confirm regenerate", type="primary"):
            st.session_state.pop(confirm_key, None)
            with st.spinner("Regenerating with Fable 5…"):
                try:
                    review, _usage = generate_weekly_review(monday)
                    if review["empty"]:
                        st.markdown(
                            empty_state("This week has no trades anymore."),
                            unsafe_allow_html=True,
                        )
                    else:
                        save_weekly_review(review, overwrite=True)
                        st.toast("Weekly review regenerated", icon="✓")
                        st.rerun()
                except WeeklyReviewError as exc:
                    st.toast(f"Could not regenerate review: {exc}", icon="✕")
                except Exception as exc:
                    st.toast(f"Unexpected error: {exc}", icon="✕")
        if c2.button("Cancel"):
            st.session_state.pop(confirm_key, None)
            st.rerun()
    else:
        if st.button("Regenerate review"):
            st.session_state[confirm_key] = monday
            st.rerun()

# --- History of past reviews ---
st.markdown("---")
st.subheader("Past Reviews")
history = list_weekly_reviews()
if not history:
    st.caption("No saved reviews yet.")
else:
    for row in history:
        stats = row.get("stats") or {}
        label = (
            f"Week of {row['week_start']} · "
            f"P/L ${stats.get('total_pnl', 0.0):,.2f} · "
            f"Win {stats.get('win_rate', 0.0):.0%}"
        )
        with st.expander(label):
            _render_review(row)
