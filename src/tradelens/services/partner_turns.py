"""One AI Partner turn, owner-scoped, ticketed and billed exactly once.

The order is fixed and every step before the provider call is free:

    1. validate the question and the client turn id
    2. verify the whole signed transcript (partner_transcript)
    3. build the owner-scoped context (zero trades / foreign trade /
       full conversation are refused here)
    4. take the text-free ticket — the atomic per-owner limit AND the
       duplicate-submit check, both under the owner-row lock
    5. call the partner (usage reported before any refusal or guard)
    6. sign the question and the reply the trader will actually see
       (after the scope guard) onto the chain
    7. complete or fail the ticket

A double submit is decided at step 4, before the partner is reachable. The
ticket row carries no conversation text: payload "{}", a digest key, and a
fixed result/error code. No conversation is stored anywhere.

What duplicate protection does and does not promise (plan D5): ONE paid call
per in-flight send — one `client_turn_id`, whether double-submitted, raced by
two tabs, or replayed. It does NOT promise one paid call per question. A
failed attempt's ticket answers its id with `DuplicateTurn` for good, so a
retry is a new attempt with a fresh id; and if the provider answered and was
billed but the response was lost on the way to the browser, that retry calls
the provider a second time. This is deliberate: the Partner does not persist
reply content, so there is no stored answer to hand back instead, and keeping
one would be the server-side transcript this service exists not to have. Both
calls are usage-logged and both count against the owner's limit.

No Streamlit imports here.
"""

from __future__ import annotations

import base64
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from src.tradelens.api import jobs, storage
from src.tradelens.services import partner
from src.tradelens.services import partner_transcript as pt
from src.tradelens.services.ai_analysis_service import get_analysis_for_trade
from src.tradelens.services.cost import log_ai_usage
from src.tradelens.services.ownership import require_user_id
from src.tradelens.services.partner_context import build_global_partner_context
from src.tradelens.services.strategy import get_active_strategy
from src.tradelens.services.trade_service import get_trade

KIND = "partner_turn"
MAX_QUESTION_CHARS = 2000
MAX_PARTNER_TURNS_PER_WINDOW = 60
PARTNER_WINDOW_HOURS = 24

RESULT_OK = "partner:ok"
RESULT_ERROR = "partner_error"

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_CLIENT_TURN_ID = re.compile(r"^[A-Za-z0-9_-]{16,64}$")

_log = logging.getLogger(__name__)


class InvalidQuestion(ValueError):
    """The request was refused before anything ran. `problem` is a fixed code."""

    def __init__(self, field: str, problem: str) -> None:
        super().__init__("{}:{}".format(field, problem))
        self.field = field
        self.problem = problem


class NoCompletedTrades(Exception):
    """The global partner has nothing to reflect on yet."""


class TradeNotFound(LookupError):
    """Missing or not this owner's — indistinguishable on purpose."""


class ConversationFull(Exception):
    """The transcript cannot grow past MAX_TRANSCRIPT_TURNS."""


class RateLimited(Exception):
    """This owner's rolling limit for paid Partner turns is reached."""


class DuplicateTurn(Exception):
    """This exact turn was already submitted; the provider is not called again."""


@dataclass(frozen=True)
class PartnerTurnResult:
    conversation_id: str
    user_turn: pt.TranscriptTurn
    assistant_turn: pt.TranscriptTurn
    evidence: tuple
    screenshot_attached: bool


def _now() -> int:
    return int(time.time())


def _clean_question(question) -> str:
    if not isinstance(question, str):
        raise InvalidQuestion("question", "invalid")
    text = question.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise InvalidQuestion("question", "required")
    if len(text) > MAX_QUESTION_CHARS:
        raise InvalidQuestion("question", "too_long")
    if _CONTROL.search(text):
        raise InvalidQuestion("question", "invalid_characters")
    return text


def _check_client_turn_id(client_turn_id) -> str:
    if not isinstance(client_turn_id, str) or not _CLIENT_TURN_ID.match(client_turn_id):
        raise InvalidQuestion("client_turn_id", "invalid")
    return client_turn_id


def _verified_history(
    owner: int, conversation_id: Optional[str], transcript, mode: str
) -> Tuple[str, list]:
    """(conversation id, role/content history) — or TranscriptInvalid."""
    if conversation_id is None:
        if transcript:
            raise pt.TranscriptInvalid()
        return pt.new_conversation_id(), []
    history = pt.verify_transcript(
        transcript, owner=owner, conv=conversation_id, mode=mode, now=_now()
    )
    if not history:
        # An existing conversation id with no turns is not a conversation.
        raise pt.TranscriptInvalid()
    if len(transcript) + 2 > pt.MAX_TRANSCRIPT_TURNS:
        raise ConversationFull()
    return conversation_id, history


def _take_ticket(owner: int, conv: str, position: int, client_turn_id: str) -> int:
    since = datetime.now(timezone.utc) - timedelta(hours=PARTNER_WINDOW_HOURS)
    ticket, created = jobs.enqueue_with_limit(
        owner,
        KIND,
        pt.turn_key(conv, position, client_turn_id),
        {},
        since=since,
        limit=MAX_PARTNER_TURNS_PER_WINDOW,
        initial_status="running",
    )
    if ticket is None:
        raise RateLimited()
    if not created:
        raise DuplicateTurn()
    return ticket


def _log_usage(owner: int):
    def log(usage) -> None:
        # Bookkeeping must never cost the trader the answer.
        try:
            log_ai_usage("AI Partner", usage, user_id=owner)
        except Exception as exc:  # noqa: BLE001
            _log.error("AI Partner usage logging failed (%s)", type(exc).__name__)

    return log


def _finish(ticket: int, ok: bool) -> None:
    try:
        if ok:
            jobs.complete(ticket, RESULT_OK)
        else:
            jobs.fail(ticket, RESULT_ERROR)
    except Exception as exc:  # noqa: BLE001 — never mask the turn's own outcome
        _log.error("AI Partner ticket close failed (%s)", type(exc).__name__)


def _converse(
    owner: int,
    *,
    mode: str,
    conv: str,
    transcript: list,
    history: list,
    question: str,
    client_turn_id: str,
    reflective_context: str = "",
    trade_context: str = "",
    strategy_input=None,
    image_png_b64: Optional[str] = None,
    per_trade_qa: bool = False,
    supplied_conversation_id: Optional[str] = None,
) -> Tuple[pt.TranscriptTurn, pt.TranscriptTurn]:
    position = len(transcript)
    # The duplicate key must be the same for a repeated submit. For a NEW
    # conversation `conv` is freshly generated on every request, so keying on
    # it would give a double-clicked first question two different keys and
    # two paid calls. Key on what the REQUEST supplied: its conversation id,
    # or a fixed per-mode marker when it started a new one. The browser reuses
    # one client_turn_id per question, so a resend is the same key.
    key_base = supplied_conversation_id or "new:{}".format(mode)
    ticket = _take_ticket(owner, key_base, position, client_turn_id)
    ok = False
    try:
        reply, _usage = partner.partner_reply(
            history + [{"role": "user", "content": question}],
            reflective_context=reflective_context,
            trade_context=trade_context,
            strategy_input=strategy_input,
            image_png_b64=image_png_b64,
            per_trade_qa=per_trade_qa,
            on_usage=_log_usage(owner),
        )
        now = _now()
        user_turn = pt.sign_turn(
            owner=owner,
            conv=conv,
            mode=mode,
            idx=position,
            role="user",
            text=question,
            prev_mac=pt.chain_head(transcript),
            iat=now,
        )
        # `reply` is what the trader will see: already through the scope
        # guard. Signing it (not the raw model output) is what makes the next
        # turn's history the history the trader was actually shown.
        assistant_turn = pt.sign_turn(
            owner=owner,
            conv=conv,
            mode=mode,
            idx=position + 1,
            role="assistant",
            text=reply,
            prev_mac=user_turn.mac,
            iat=now,
        )
        ok = True
        return user_turn, assistant_turn
    finally:
        _finish(ticket, ok)


def run_global_turn(
    user_id: int,
    *,
    question,
    transcript,
    conversation_id: Optional[str],
    client_turn_id,
) -> PartnerTurnResult:
    owner = require_user_id(user_id)
    text = _clean_question(question)
    client_turn_id = _check_client_turn_id(client_turn_id)
    mode = "global"
    conv, history = _verified_history(owner, conversation_id, transcript, mode)

    context = build_global_partner_context(user_id=owner)
    if int(context.completed_trade_count or 0) <= 0:
        raise NoCompletedTrades()

    user_turn, assistant_turn = _converse(
        owner,
        mode=mode,
        conv=conv,
        transcript=list(transcript or []),
        history=history,
        question=text,
        client_turn_id=client_turn_id,
        supplied_conversation_id=conversation_id,
        reflective_context=context.context_text,
        strategy_input=context.strategy_profile,
        per_trade_qa=False,
    )
    return PartnerTurnResult(
        conversation_id=conv,
        user_turn=user_turn,
        assistant_turn=assistant_turn,
        evidence=tuple(context.evidence_sources),
        screenshot_attached=False,
    )


def _own_screenshot_png_b64(owner: int, trade) -> Optional[str]:
    """The trade's newest owned, normalised screenshot — or None.

    Chosen here, never by the browser: the request carries a boolean, not an
    id or a key. Read through the owner-scoped storage path only.
    """
    shots = sorted(
        getattr(trade, "screenshots", None) or [],
        key=lambda s: s.id,
        reverse=True,
    )
    for shot in shots:
        try:
            if not storage.screenshot_belongs_to_trade(owner, shot.id, trade.id):
                continue
            data = storage.read_owned_final_object(owner, shot.id)
        except Exception as exc:  # noqa: BLE001 — reported as not attached
            _log.error("AI Partner screenshot read failed (%s)", type(exc).__name__)
            return None
        if data:
            return base64.b64encode(data).decode("ascii")
        return None
    return None


def run_trade_turn(
    user_id: int,
    trade_id: int,
    *,
    question,
    transcript,
    conversation_id: Optional[str],
    client_turn_id,
    include_screenshot: bool = False,
) -> PartnerTurnResult:
    owner = require_user_id(user_id)
    if isinstance(trade_id, bool) or not isinstance(trade_id, int) or trade_id <= 0:
        raise TradeNotFound()
    text = _clean_question(question)
    client_turn_id = _check_client_turn_id(client_turn_id)
    mode = "trade:{}".format(trade_id)
    conv, history = _verified_history(owner, conversation_id, transcript, mode)

    trade = get_trade(trade_id, owner)
    if trade is None:
        raise TradeNotFound()
    analysis = get_analysis_for_trade(trade_id, user_id=owner)
    image = (
        _own_screenshot_png_b64(owner, trade) if include_screenshot is True else None
    )

    user_turn, assistant_turn = _converse(
        owner,
        mode=mode,
        conv=conv,
        transcript=list(transcript or []),
        history=history,
        question=text,
        client_turn_id=client_turn_id,
        supplied_conversation_id=conversation_id,
        trade_context=partner.build_trade_context(trade, analysis),
        strategy_input=get_active_strategy(owner),
        image_png_b64=image,
        per_trade_qa=True,
    )
    return PartnerTurnResult(
        conversation_id=conv,
        user_turn=user_turn,
        assistant_turn=assistant_turn,
        evidence=(),
        screenshot_attached=image is not None,
    )
