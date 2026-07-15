import sys
import tempfile
from pathlib import Path

# parents[5] of src/tradelens/ui/pages/*.py  →  project root
_root = str(Path(__file__).resolve().parents[5])
if _root not in sys.path:
    sys.path.insert(0, _root)

import html  # noqa: E402

import streamlit as st  # noqa: E402

from src.tradelens.services.ai_analysis_service import (  # noqa: E402
    get_analysis_for_trade,
)
from src.tradelens.services.ai_client import encode_image  # noqa: E402
from src.tradelens.services.partner import (  # noqa: E402
    PartnerError,
    build_trade_context,
    partner_reply,
)
from src.tradelens.services.strategy import get_active_strategy  # noqa: E402
from src.tradelens.services.trade_service import get_trades  # noqa: E402
from src.tradelens.ui.components.demo_banner import render_demo_banner  # noqa: E402
from src.tradelens.ui.components.theme import inject_css  # noqa: E402
from src.tradelens.ui.components.ui import empty_state, section_header  # noqa: E402

# ── Session-state contract (must survive any rewrite) ──────────────
#   convo_key  = "partner_history_{trade.id}" | "partner_history_upload"
#       -> list[dict] of {"role": "user"|"assistant", "content": str}
#   cost_key   = f"{convo_key}_cost"
#       -> {"tokens_in": int, "tokens_out": int, "cost": float}
# The partner_reply() service consumes the history list verbatim.

st.set_page_config(page_title="AI Partner", layout="wide")
inject_css()
render_demo_banner()
st.markdown(
    section_header(
        "AI Trading Partner",
        "A senior SMC/ICT partner reviews a completed trade and your process — "
        "post-trade reflection only: no signals, no predictions.",
    ),
    unsafe_allow_html=True,
)

trades = get_trades()

# --- Pick the trade under review: a logged trade OR an uploaded screenshot ---
mode = st.radio("Review source", ["Logged trade", "Upload screenshot"], horizontal=True)

trade_context = ""
image_b64 = None
convo_key = None


def _trade_label(t) -> str:
    return f"#{t.id} · {t.trade_date or '?'} · {t.asset} · {t.result or '—'}"


if mode == "Logged trade":
    if not trades:
        st.markdown(
            empty_state(
                "No trades logged yet — log a trade first, or upload a screenshot.",
                cta_label="Log a trade",
                cta_href="/NewTrade",
            ),
            unsafe_allow_html=True,
        )
        st.stop()

    trade = st.selectbox(
        "Pick a trade to review", options=trades, format_func=_trade_label
    )
    convo_key = f"partner_history_{trade.id}"

    analysis = get_analysis_for_trade(trade.id)
    trade_context = build_trade_context(trade, analysis)

    shots = sorted(
        trade.screenshots or [], key=lambda s: s.uploaded_at or "", reverse=True
    )
    if shots and Path(shots[0].file_path).exists():
        st.image(shots[0].file_path, width=360)
        try:
            image_b64 = encode_image(shots[0].file_path)
        except Exception:  # chart is optional context
            image_b64 = None
else:
    upload = st.file_uploader(
        "Upload a screenshot of a finished trade", type=["png", "jpg", "jpeg"]
    )
    if upload is None:
        st.markdown(
            empty_state("Upload a screenshot to start the review."),
            unsafe_allow_html=True,
        )
        st.stop()

    convo_key = "partner_history_upload"
    st.image(upload, width=360)
    suffix = Path(upload.name).suffix or ".png"
    tmp = Path(tempfile.gettempdir()) / f"tradelens_partner_upload{suffix}"
    tmp.write_bytes(upload.getbuffer())
    try:
        image_b64 = encode_image(str(tmp))
    except Exception:
        image_b64 = None
    trade_context = (
        "COMPLETED TRADE UNDER REVIEW: provided as an uploaded screenshot "
        "(no logged trade row). Read the chart for HTF bias, killzone, liquidity "
        "sweeps, FVGs, order blocks, and BOS/CHoCH."
    )

strategy_profile = get_active_strategy()

# --- Conversation state, keyed by trade / source (contract above) ---
cost_key = f"{convo_key}_cost"
history = st.session_state.setdefault(convo_key, [])
costs = st.session_state.setdefault(
    cost_key, {"tokens_in": 0, "tokens_out": 0, "cost": 0.0}
)

# --- Sidebar: per-conversation cost + reset ---
with st.sidebar:
    st.header("This conversation")
    st.metric("Tokens in", f"{costs['tokens_in']:,}")
    st.metric("Tokens out", f"{costs['tokens_out']:,}")
    st.metric("Cost", f"${costs['cost']:.4f}")
    if st.button("Clear conversation", width="stretch"):
        st.session_state[convo_key] = []
        st.session_state[cost_key] = {"tokens_in": 0, "tokens_out": 0, "cost": 0.0}
        st.rerun()

# --- Render history as scoped markdown bubbles. We deliberately avoid the
#     built-in Streamlit chat widgets here: they ignore the injected dark-theme
#     CSS and reintroduce the default blue. Bubbles use theme .tl-chat-* classes.
for m in history:
    if m["role"] == "user":
        st.markdown(
            f'<div class="tl-chat-user">{html.escape(m["content"])}</div>',
            unsafe_allow_html=True,
        )
    else:
        # AI content is markdown — wrap in the glass bubble; blank lines let
        # Streamlit's markdown renderer format the body inside the div.
        st.markdown(
            f'<div class="tl-chat-ai">\n\n{m["content"]}\n\n</div>',
            unsafe_allow_html=True,
        )

# --- New turn ---
with st.form("partner_turn", clear_on_submit=True):
    prompt = st.text_input(
        "Ask your partner about this trade…",
        key="partner_prompt",
        label_visibility="collapsed",
        placeholder="Ask your partner about this trade…",
    )
    submitted = st.form_submit_button("Send", type="primary")

if submitted and prompt:
    history.append({"role": "user", "content": prompt})
    with st.spinner("Reviewing with AI…"):
        try:
            reply, usage = partner_reply(
                history,
                trade_context=trade_context,
                strategy_profile=strategy_profile,
                image_b64=image_b64,
            )
            history.append({"role": "assistant", "content": reply})
            costs["tokens_in"] += usage.tokens_in
            costs["tokens_out"] += usage.tokens_out
            costs["cost"] += usage.estimated_cost_usd
            st.rerun()
        except PartnerError as exc:
            st.toast(f"Partner unavailable: {exc}", icon="❌")
        except Exception as exc:
            st.toast(f"Unexpected error: {exc}", icon="❌")
