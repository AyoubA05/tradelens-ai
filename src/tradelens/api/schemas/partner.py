"""The AI Partner wire contract.

Every model is `_Strict` (`extra="forbid"`, `strict=True`), so a renamed or
added field is a loud failure rather than a silently dropped turn.

The transcript crosses the wire in both directions and is the browser's only
copy of the conversation — the server stores none of it. A turn's `mac` is
what makes that safe; nothing here may be widened to accept an unsigned turn.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import Field

from src.tradelens.api.schemas.trades import _Strict

# Bounds mirror services/partner_transcript.py and services/partner_turns.py.
MAX_TRANSCRIPT_TURNS = 40
MAX_TURN_TEXT_CHARS = 20_000
MAX_QUESTION_CHARS = 2000


class PartnerTranscriptTurn(_Strict):
    idx: int = Field(ge=0, le=MAX_TRANSCRIPT_TURNS - 1)
    role: Literal["user", "assistant"]
    text: str = Field(max_length=MAX_TURN_TEXT_CHARS)
    iat: int
    mac: str = Field(min_length=64, max_length=64)


class PartnerTurnRequest(_Strict):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    conversation_id: Optional[str] = Field(default=None, max_length=64)
    transcript: List[PartnerTranscriptTurn] = Field(
        default_factory=list, max_length=MAX_TRANSCRIPT_TURNS
    )
    client_turn_id: str = Field(min_length=16, max_length=64)


class TradePartnerTurnRequest(PartnerTurnRequest):
    """`include_screenshot` is a boolean and nothing else.

    The service also requires exactly `True` (a stringified "false" is the
    classic way a flag turns itself on); `strict=True` refuses it here first.
    The request never names a screenshot: the server chooses the trade's own.
    """

    include_screenshot: bool = False


class PartnerEvidence(_Strict):
    kind: Literal["journal", "trade", "strategy"]
    label: str
    occurred_on: Optional[str]
    trade_id: Optional[int]


class PartnerTurnResponse(_Strict):
    conversation_id: str
    turns: List[PartnerTranscriptTurn]
    evidence: List[PartnerEvidence]
    screenshot_attached: bool
