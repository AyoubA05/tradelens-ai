"""`/v1/partner/turns` and `/v1/trades/{id}/partner/turns` — one AI Partner turn.

Synchronous: one request, one reply, no stored conversation. The browser holds
the transcript and returns it signed; the server verifies the whole chain
before anything is spent.

Status mapping, fixed and never carrying exception text:

* 409 `transcript_invalid` — the chain did not verify (missing, duplicated,
  reordered, edited, cross-conversation or sibling-fork turns all land here,
  deliberately indistinguishable).
* 409 `conversation_full` — the transcript cannot grow further.
* 409 `no_trades` — the global partner has nothing to reflect on yet.
* 409 `duplicate_turn` — this exact turn was already submitted; the provider
  was NOT called again.
* 429 `rate_limited` — the owner's rolling limit for paid turns.
* 404 — missing or another owner's trade, byte-identical either way.
* 422 — a field problem, by field and fixed code, never by value.
* 503 `partner_unavailable` — the model refused or was unreachable.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from src.tradelens.api.deps import current_user
from src.tradelens.api.schemas.partner import (
    PartnerEvidence,
    PartnerTranscriptTurn,
    PartnerTurnRequest,
    PartnerTurnResponse,
    TradePartnerTurnRequest,
)
from src.tradelens.services import partner_turns
from src.tradelens.services.partner import PartnerError
from src.tradelens.services.partner_transcript import TranscriptInvalid

router = APIRouter(prefix="/v1", tags=["partner"])


def _conflict(code: str) -> HTTPException:
    return HTTPException(status_code=409, detail=code)


def _invalid(exc: partner_turns.InvalidQuestion) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": [{"field": exc.field, "problem": exc.problem}]},
    )


def _wire_turn(turn) -> PartnerTranscriptTurn:
    return PartnerTranscriptTurn(
        idx=turn.idx, role=turn.role, text=turn.text, iat=turn.iat, mac=turn.mac
    )


def _evidence(sources) -> list:
    out = []
    for source in sources:
        out.append(
            PartnerEvidence(
                kind=source.kind,
                label=source.label,
                occurred_on=source.occurred_on,
                # Only a trade row is linkable; a journal note IS a trade row.
                trade_id=(
                    int(source.record_id)
                    if source.kind in ("trade", "journal")
                    else None
                ),
            )
        )
    return out


def _response(result) -> PartnerTurnResponse:
    return PartnerTurnResponse(
        conversation_id=result.conversation_id,
        turns=[_wire_turn(result.user_turn), _wire_turn(result.assistant_turn)],
        evidence=_evidence(result.evidence),
        screenshot_attached=result.screenshot_attached,
    )


def _run(call):
    """One place for the refusal mapping, so both routes answer identically."""
    try:
        return _response(call())
    except partner_turns.InvalidQuestion as exc:
        return _invalid(exc)
    except TranscriptInvalid:
        raise _conflict("transcript_invalid")
    except partner_turns.ConversationFull:
        raise _conflict("conversation_full")
    except partner_turns.NoCompletedTrades:
        raise _conflict("no_trades")
    except partner_turns.DuplicateTurn:
        raise _conflict("duplicate_turn")
    except partner_turns.RateLimited:
        raise HTTPException(status_code=429, detail="rate_limited")
    except partner_turns.TradeNotFound:
        raise HTTPException(status_code=404, detail="Not Found")
    except PartnerError:
        # The model's own reason is never forwarded: it can carry provider
        # detail, and none of it is actionable to a trader.
        raise HTTPException(status_code=503, detail="partner_unavailable")


@router.post(
    "/partner/turns",
    response_model=PartnerTurnResponse,
    responses={404: {}, 409: {}, 422: {}, 429: {}, 503: {}},
)
def post_partner_turn(
    payload: PartnerTurnRequest, user_id: int = Depends(current_user)
):
    """One turn of the global, journal-grounded conversation."""
    return _run(
        lambda: partner_turns.run_global_turn(
            user_id,
            question=payload.question,
            transcript=[t.model_dump() for t in payload.transcript],
            conversation_id=payload.conversation_id,
            client_turn_id=payload.client_turn_id,
        )
    )


@router.post(
    "/trades/{trade_id}/partner/turns",
    response_model=PartnerTurnResponse,
    responses={404: {}, 409: {}, 422: {}, 429: {}, 503: {}},
)
def post_trade_partner_turn(
    trade_id: int,
    payload: TradePartnerTurnRequest,
    user_id: int = Depends(current_user),
):
    """One turn about ONE completed trade of this owner's."""
    return _run(
        lambda: partner_turns.run_trade_turn(
            user_id,
            trade_id,
            question=payload.question,
            transcript=[t.model_dump() for t in payload.transcript],
            conversation_id=payload.conversation_id,
            client_turn_id=payload.client_turn_id,
            include_screenshot=payload.include_screenshot,
        )
    )
