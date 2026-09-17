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
from typing import Callable, Optional

from src.tradelens.services.ai_client import AIUnavailable, Usage, chat, load_prompt
from src.tradelens.services.ownership import require_user_id
from src.tradelens.services.prompt_inputs import prompt_scalar, sanitised_strategy
from src.tradelens.services.reflection_guard import reject_forward_looking
from src.tradelens.services.trade_service import get_trades
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

# The call's effort literal; None means the ai_client default. Part of the
# effective-input fingerprint (Phase 10A, C2).
DAILY_EFFORT = None

# Job-backed Daily Debrief (Phase 10A, R1/R3/R4).
DAILY_JOB_KIND = "daily_debrief"
MAX_DAILY_PER_WINDOW = 20
REVIEW_WINDOW_HOURS = 24

_UNSET = object()

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
    Every trader-authored string goes through `prompt_inputs.prompt_scalar`.
    """
    rows = sorted(trades, key=lambda t: str(getattr(t, "trade_date", "") or ""))
    rows = rows[-_MAX_TRADES:]
    payload = []
    for t in rows:
        row = {}
        for f in _PAYLOAD_FIELDS:
            value = getattr(t, f, None)
            # Trader-typed text (setup, emotions, ...) is prompt data too.
            row[f] = prompt_scalar(value) if isinstance(value, str) else value
        try:
            tags = json.loads(getattr(t, "mistake_tags", None) or "[]")
            row["mistake_tags"] = [
                prompt_scalar(tag) if isinstance(tag, str) else tag for tag in tags
            ]
        except (json.JSONDecodeError, TypeError):
            row["mistake_tags"] = []
        notes = getattr(t, "notes", None)
        if isinstance(notes, str) and notes.strip():
            row["notes"] = prompt_scalar(notes.strip())[:_MAX_NOTE_CHARS]
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


def _model_input_from_trades(
    trades: list, strategy_profile: Optional[dict], period_label: str
) -> dict:
    """The exact object the debrief user message is built from (decision C2)."""
    return {
        "period_label": period_label,
        "stats": _week_stats(_trades_to_df(trades)),
        "trades": build_trades_payload(trades),
        "total_trades": len(trades),
        "strategy_profile": sanitised_strategy(strategy_profile) or None,
    }


def build_daily_model_input(
    user_id: int,
    day: str,
    *,
    strategy_profile=_UNSET,
    trades: Optional[list] = None,
    as_of=None,
) -> dict:
    """The owner's model input for one trading day, plus its source trade ids.

    `strategy_profile` defaults to the owner's active profile; `trades` to the
    owner's trades on `day` (the worker passes rows read through its locking
    session). Rows are ordered by id first so same-date ties are stable.
    Trades dated after `as_of` (default: `review_inputs.review_as_of`) are
    excluded defensively — the router never offers a future day (C6).
    """
    from src.tradelens.services import review_inputs

    owner = require_user_id(user_id)
    if as_of is None:
        as_of = review_inputs.review_as_of(owner)
    if trades is None:
        trades = get_trades(start_date=day, end_date=day, user_id=owner)
    if strategy_profile is _UNSET:
        from src.tradelens.services.strategy import get_active_strategy

        strategy_profile = get_active_strategy(owner)
    rows = sorted(
        review_inputs.on_or_before(list(trades), as_of), key=lambda t: int(t.id)
    )
    model_input = _model_input_from_trades(rows, strategy_profile, f"Trading day {day}")
    model_input["source_trade_ids"] = [int(t.id) for t in rows]
    return model_input


def generate_debrief(
    trades: Optional[list] = None,
    strategy_profile: Optional[dict] = None,
    period_label: str = "Trading session",
    *,
    on_usage: Optional[Callable[[Usage], None]] = None,
    model_input: Optional[dict] = None,
    corrections_block: Optional[str] = None,
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
    if model_input is None:
        model_input = _model_input_from_trades(
            list(trades or []), strategy_profile, period_label
        )
    stats = model_input["stats"]

    if not model_input["total_trades"]:
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

    payload = model_input["trades"]
    total = model_input["total_trades"]
    capped = (
        f" (most recent {len(payload)} of {total} shown)"
        if total > len(payload)
        else ""
    )
    profile = model_input["strategy_profile"]
    strategy_block = (
        json.dumps(profile, indent=2, default=str) if profile else _NO_PROFILE_BLOCK
    )
    user_message = (
        "POST-SESSION DEBRIEF REQUEST\n\n"
        f"Period: {model_input['period_label']}\n\n"
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
        **({} if DAILY_EFFORT is None else {"effort": DAILY_EFFORT}),
        corrections_block=corrections_block,
    )
    # Recorded the moment the provider answers: a response that then fails
    # validation or the guard was still billed.
    if on_usage is not None:
        on_usage(usage)

    if isinstance(content, AIUnavailable):
        raise DebriefError(content.reason)

    _validate_sections(content)
    # Lexical defense-in-depth, not a semantic guarantee (decision C4).
    reject_forward_looking(content, DebriefError)
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
