"""
Session debrief service — a coach-like post-session review over a set of
CLOSED trades: a completed trading day (Daily Debrief) or any cluster the
trader selected (multi-trade summary on the Journal page).

Reuses the weekly-review machinery: the same trade→DataFrame bridge and
headline-stats helper, the central ai_client (corrections injected on every
call), and the same DEMO_MODE zero-spend path. The Strategy Profile is folded
into the user message when present; otherwise the prompt's general framework
applies. Post-trade reflection only — never signals. No Streamlit imports here.
"""

import json
from typing import Optional

from src.tradelens.services.ai_client import AIUnavailable, Usage, chat, load_prompt
from src.tradelens.services.weekly import _trades_to_df, _week_stats

_REQUIRED_SECTIONS = [
    "### Session Summary",
    "### Discipline & Rule Adherence",
    "### Emotional Review",
    "### Recurring Patterns",
    "### Improvement Actions",
]

# Compact per-trade fields sent to the model (JSON-safe, prompt-budget-aware).
_PAYLOAD_FIELDS = (
    "trade_date",
    "asset",
    "direction",
    "timeframe",
    "session",
    "killzone",
    "setup_type",
    "confirmation_model",
    "htf_bias",
    "result",
    "pnl",
    "rr_realized",
    "followed_rules",
    "emotions_before",
    "emotions_during",
    "emotions_after",
    "ai_grade",
    "user_grade",
)

_MAX_TRADES = 40  # newest trades kept when the selection is larger
_MAX_NOTE_CHARS = 200

# Canned debrief returned in DEMO_MODE (zero spend) — satisfies the contract.
_DEMO_DEBRIEF_MD = "\n\n".join(
    f"{h}\n\n_DEMO MODE_ — sample reflection for this section."
    for h in _REQUIRED_SECTIONS
)

_NO_PROFILE_BLOCK = (
    "No strategy profile provided — use the general review framework "
    "(price action, risk management, entry quality, exit quality, "
    "emotional discipline, journaling quality)."
)


class DebriefError(Exception):
    """Raised when the AI debrief is unavailable or missing required sections."""


def build_trades_payload(trades: list) -> list:
    """Compact JSON-safe dicts for the prompt, oldest first, capped at 40.

    mistake_tags (a JSON string column) is parsed to a list; notes are
    truncated so one verbose journal entry can't blow the prompt budget.
    """
    rows = sorted(trades, key=lambda t: str(getattr(t, "trade_date", "") or ""))
    rows = rows[-_MAX_TRADES:]
    payload = []
    for t in rows:
        row = {f: getattr(t, f, None) for f in _PAYLOAD_FIELDS}
        try:
            row["mistake_tags"] = json.loads(getattr(t, "mistake_tags", None) or "[]")
        except (json.JSONDecodeError, TypeError):
            row["mistake_tags"] = []
        notes = getattr(t, "notes", None)
        if isinstance(notes, str) and notes.strip():
            row["notes"] = notes.strip()[:_MAX_NOTE_CHARS]
        payload.append(row)
    return payload


def _validate_sections(markdown: str) -> None:
    positions = []
    for section in _REQUIRED_SECTIONS:
        idx = markdown.find(section)
        if idx == -1:
            raise DebriefError(f"Debrief is missing required section: '{section}'")
        positions.append(idx)
    if positions != sorted(positions):
        raise DebriefError("Debrief sections are out of order.")


def generate_debrief(
    trades: list,
    strategy_profile: Optional[dict] = None,
    period_label: str = "Trading session",
) -> tuple[dict, Usage]:
    """Generate a coach-like debrief over a set of closed trades.

    An empty set returns an empty result WITHOUT any API call. Returns
    (debrief_dict, usage); debrief_dict keys: empty, content_md,
    thinking_summary, stats, cost_usd — the same shape the weekly review uses,
    so UI rendering helpers can be shared.

    Raises:
        FileNotFoundError: prompts/debrief_v1.txt missing.
        DebriefError: AI unavailable or response missing required sections.
    """
    df = _trades_to_df(trades)
    stats = _week_stats(df)

    if not trades:
        return (
            {
                "empty": True,
                "content_md": None,
                "thinking_summary": None,
                "stats": stats,
                "cost_usd": 0.0,
            },
            Usage("none", 0, 0, 0, 0.0, 0.0),
        )

    payload = build_trades_payload(trades)
    capped = (
        f" (most recent {len(payload)} of {len(trades)} shown)"
        if len(trades) > len(payload)
        else ""
    )
    strategy_block = (
        json.dumps(strategy_profile, indent=2, default=str)
        if strategy_profile
        else _NO_PROFILE_BLOCK
    )
    user_message = (
        "POST-SESSION DEBRIEF REQUEST\n\n"
        f"Period: {period_label}\n\n"
        f"Headline stats:\n{json.dumps(stats, indent=2, default=str)}\n\n"
        f"Trades{capped}:\n{json.dumps(payload, indent=2, default=str)}\n\n"
        f"Strategy profile:\n{strategy_block}\n\n"
        "Write the 5-section debrief now."
    )

    # Past corrections are injected centrally by ai_client for every call.
    content, usage = chat(
        user_message=user_message,
        system_message=load_prompt("debrief_v1"),
        demo_response=_DEMO_DEBRIEF_MD,
    )

    if isinstance(content, AIUnavailable):
        raise DebriefError(content.reason)

    _validate_sections(content)
    return (
        {
            "empty": False,
            "content_md": content,
            "thinking_summary": usage.thinking_summary,
            "stats": stats,
            "cost_usd": usage.estimated_cost_usd,
        },
        usage,
    )
