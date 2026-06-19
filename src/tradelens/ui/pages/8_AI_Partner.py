import sys
import tempfile
from pathlib import Path

# parents[4] of src/tradelens/ui/pages/*.py  →  project root
_root = str(Path(__file__).resolve().parents[4])
if _root not in sys.path:
    sys.path.insert(0, _root)

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

st.set_page_config(page_title="AI Partner", page_icon="🤝", layout="wide")
st.title("🤝 AI Trading Partner")
st.caption(
    "A senior SMC/ICT partner reviews a completed trade and your process — "
    "HTF bias, killzone, sweeps, FVGs, order blocks, BOS/CHoCH, entry & exit "
    "quality. Post-trade reflection only: no signals, no predictions."
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
        st.info("No trades logged yet. Log a trade first, or upload a screenshot.")
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
        except Exception:  # noqa: BLE001 — chart is optional context
            image_b64 = None
else:
    upload = st.file_uploader(
        "Upload a screenshot of a finished trade", type=["png", "jpg", "jpeg"]
    )
    if upload is None:
        st.info("Upload a screenshot to start the review.")
        st.stop()

    convo_key = "partner_history_upload"
    st.image(upload, width=360)
    suffix = Path(upload.name).suffix or ".png"
    tmp = Path(tempfile.gettempdir()) / f"tradelens_partner_upload{suffix}"
    tmp.write_bytes(upload.getbuffer())
    try:
        image_b64 = encode_image(str(tmp))
    except Exception:  # noqa: BLE001
        image_b64 = None
    trade_context = (
        "COMPLETED TRADE UNDER REVIEW: provided as an uploaded screenshot "
        "(no logged trade row). Read the chart for HTF bias, killzone, liquidity "
        "sweeps, FVGs, order blocks, and BOS/CHoCH."
    )

strategy_profile = get_active_strategy()

# --- Conversation state, keyed by trade / source ---
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
    if st.button("🧹 Clear conversation", use_container_width=True):
        st.session_state[convo_key] = []
        st.session_state[cost_key] = {"tokens_in": 0, "tokens_out": 0, "cost": 0.0}
        st.rerun()

# --- Render history ---
for m in history:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# --- New turn ---
prompt = st.chat_input("Ask your partner about this trade…")
if prompt:
    history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Reviewing…"):
            try:
                reply, usage = partner_reply(
                    history,
                    trade_context=trade_context,
                    strategy_profile=strategy_profile,
                    image_b64=image_b64,
                )
                st.markdown(reply)
                history.append({"role": "assistant", "content": reply})
                costs["tokens_in"] += usage.tokens_in
                costs["tokens_out"] += usage.tokens_out
                costs["cost"] += usage.estimated_cost_usd
                st.rerun()
            except PartnerError as exc:
                st.error(f"Partner unavailable: {exc}")
            except Exception as exc:  # noqa: BLE001 — surface any failure gracefully
                st.error(f"Unexpected error: {exc}")
