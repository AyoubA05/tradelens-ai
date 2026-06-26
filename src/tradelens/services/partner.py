"""
AI trading-partner service — multi-turn review of a COMPLETED trade.

A senior SMC/ICT partner reviews a finished trade and the trader's process. It
speaks the precise language (HTF bias, killzone, liquidity sweep, FVG, order
block, BOS, CHoCH, confirmation model, entry/exit quality, mistake tags, rule
adherence) and is hard-scoped to post-trade reflection: no signals, no price
predictions, no "what should I trade next".

Streamlit-free. DEMO_MODE returns a canned reply (zero API spend). Correction
memory is injected centrally by ai_client — never re-injected here.
"""

import json
from typing import Optional

from src.tradelens.services.ai_client import AIUnavailable, Usage, converse, load_prompt

MAX_TURNS = 10
PARTNER_EFFORT = "medium"

# Hardcoded scope guard — ALWAYS present in the system prompt, regardless of
# trade, strategy, or conversation state. The post-check below is the backstop.
_SCOPE_GUARD = (
    "STRICT SCOPE (non-negotiable): You review COMPLETED trades and the trader's "
    "PROCESS quality only. You must NEVER provide trade signals, price predictions, "
    "forecasts, or tell the trader what to buy, sell, or trade next. If the trader "
    "asks for any of those, refuse and redirect to reviewing the completed trade. "
    "This is post-trade reflection and education — not financial advice."
)

_REDIRECT_MESSAGE = (
    "I'm your post-trade review partner — I only analyze trades you've already taken "
    "and the quality of your process. I can't give signals, predictions, or tell you "
    "what to trade next. Let's stay on this trade: walk me through your reasoning at "
    "entry and how it lined up with your HTF bias and killzone."
)

# Forward-looking / signal-seeking markers that must never appear in a reply.
_SIGNAL_MARKERS = (
    "entry tomorrow",
    "what should i trade",
    "you should buy",
    "you should sell",
    "i recommend buying",
    "i recommend selling",
    "buy now",
    "sell now",
    "trade tomorrow",
    "should i buy",
    "should i sell",
    "price will",
    "price target",
    "next trade:",
    "i predict",
    "will likely rally",
    "will likely drop",
)

_DEMO_PARTNER_REPLY = (
    "Reviewing this trade: your HTF bias was bullish and you waited for the NY AM "
    "killzone — disciplined. The entry came off an order block retest following a "
    "liquidity sweep, with BOS as your confirmation model: a clean, repeatable read. "
    "Where I'd push you is exit quality — you left R on the table by not trailing to "
    "the next FVG. No mistake tags fired and you followed your rules, so this grades "
    "as a strong process even if the result was modest. What made you exit when you did?"
)

# Trade-row fields (SMC/ICT vocabulary) surfaced into the conversation context.
_SMC_TRADE_FIELDS = [
    "trade_date",
    "asset",
    "direction",
    "result",
    "pnl",
    "rr_planned",
    "rr_realized",
    "session",
    "killzone",
    "htf_bias",
    "bias",
    "setup_type",
    "confirmation_model",
    "liquidity_sweep",
    "fvg_used",
    "order_block_used",
    "bos",
    "choch",
    "entry_type",
    "mistake_tags",
    "followed_rules",
    "entry_price",
    "stop_price",
    "exit_price",
    "notes",
]

_ANALYSIS_FIELDS = [
    "bias",
    "detected_setup",
    "trade_quality",
    "matched_strategy",
    "mistakes_json",
    "missed_opps_json",
]


class PartnerError(Exception):
    """Raised when the AI partner is unavailable (refusal, outage, missing key)."""


def _get(obj, key):
    if obj is None:
        return None
    return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)


def build_partner_system(
    strategy_profile: Optional[dict] = None, running_summary: Optional[str] = None
) -> str:
    """Assemble the system prompt. The scope guard is ALWAYS included."""
    parts = [load_prompt("partner_v2"), _SCOPE_GUARD]
    if strategy_profile:
        parts.append(
            "ACTIVE STRATEGY PROFILE:\n"
            + json.dumps(strategy_profile, indent=2, default=str)
        )
    if running_summary:
        parts.append("EARLIER CONVERSATION SUMMARY:\n" + running_summary)
    return "\n\n".join(parts)


def build_trade_context(trade, analysis=None) -> str:
    """Structured, SMC-precise block describing the completed trade under review."""
    lines = ["COMPLETED TRADE UNDER REVIEW:"]
    for field in _SMC_TRADE_FIELDS:
        val = _get(trade, field)
        if val is not None and val != "":
            lines.append(f"- {field}: {val}")
    if analysis is not None:
        analysis_lines = []
        for field in _ANALYSIS_FIELDS:
            val = _get(analysis, field)
            if val is not None and val != "":
                analysis_lines.append(f"- {field}: {val}")
        if analysis_lines:
            lines.append("AI ANALYSIS ON RECORD:")
            lines.extend(analysis_lines)
    return "\n".join(lines)


def trim_history(messages: list, max_turns: int = MAX_TURNS) -> tuple:
    """Keep the last `max_turns` messages; summarize anything older.

    Returns (trimmed_messages, running_summary). running_summary is None when the
    history is within budget. A "turn" is one message (user or assistant).
    """
    if len(messages) <= max_turns:
        return list(messages), None
    older = messages[:-max_turns]
    recent = messages[-max_turns:]
    return recent, _summarize(older)


def _summarize(older: list) -> str:
    bits = []
    for m in older:
        role = m.get("role", "?")
        content = m.get("content") or ""
        if not isinstance(content, str):
            content = str(content)
        snippet = " ".join(content.split())
        if len(snippet) > 120:
            snippet = snippet[:117] + "..."
        bits.append(f"{role}: {snippet}")
    return f"Earlier in this review ({len(older)} messages): " + " | ".join(bits)


def _apply_scope_guard(text: str) -> str:
    """Replace any signal-seeking / predictive reply with the redirect message."""
    low = text.lower()
    if any(marker in low for marker in _SIGNAL_MARKERS):
        return _REDIRECT_MESSAGE
    return text


def _to_api_messages(messages: list, image_b64: Optional[str] = None) -> list:
    """Convert history dicts to the Anthropic message shape.

    Drops any leading assistant turns so the list starts with a user turn, and
    attaches the screenshot (if any) to the first user turn as an image block.
    """
    msgs = list(messages)
    while msgs and msgs[0].get("role") == "assistant":
        msgs = msgs[1:]

    api = []
    image_attached = False
    for m in msgs:
        role = m.get("role")
        content = m.get("content")
        if role == "user" and image_b64 and not image_attached:
            api.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_b64,
                            },
                        },
                        {"type": "text", "text": content},
                    ],
                }
            )
            image_attached = True
        else:
            api.append({"role": role, "content": content})
    return api


def partner_reply(
    messages: list,
    *,
    trade_context: str = "",
    strategy_profile: Optional[dict] = None,
    image_b64: Optional[str] = None,
) -> tuple[str, Usage]:
    """
    Produce the partner's next reply for a multi-turn trade review.

    Args:
        messages: full role-tagged history ending with the latest user turn.
        trade_context: structured SMC block from build_trade_context (optional).
        strategy_profile: active Strategy Profile dict (prompt-cached).
        image_b64: base64 screenshot to include as a vision block (optional).

    Returns (reply_text, usage). The reply has already passed the scope-guard
    post-check. Raises PartnerError if the AI is unavailable.
    """
    trimmed, summary = trim_history(messages)
    system_message = build_partner_system(strategy_profile, running_summary=summary)
    if trade_context:
        system_message = f"{system_message}\n\n{trade_context}"

    api_messages = _to_api_messages(trimmed, image_b64=image_b64)

    content, usage = converse(
        api_messages,
        system_message=system_message,
        cache_system=True,  # strategy profile + scope guard cached across turns
        effort=PARTNER_EFFORT,
        demo_response=_DEMO_PARTNER_REPLY,
    )

    if isinstance(content, AIUnavailable):
        raise PartnerError(content.reason)

    return _apply_scope_guard(content), usage
