"""The AI Partner's stateless, signed, hash-chained transcript.

The browser holds the conversation; the server stores none of it. Every turn
the server accepts is returned with a MAC that binds:

    owner · conversation id · mode · position · role · sha256(exact text)
    · the previous turn's MAC · issued-at

Because each MAC covers its predecessor's MAC, a transcript is a chain, and
the only chains that verify are the prefixes the server itself issued, in
order. Verification recomputes the whole chain from ``GENESIS`` on every
request and refuses a missing, duplicated, reordered or edited turn, a turn
from another conversation, mode or owner, and a turn from a sibling
continuation of the same conversation.

The one subtlety the Group A review pinned: the verifier threads forward the
MAC IT recomputed and verified — never the MAC the browser sent for the
previous turn. Otherwise fork A's text carrying fork B's MAC, followed by
fork B's next turn, would chain.

Accepted by design (plan D4): dropping the newest complete exchanges (a valid
prefix) and resuming a conversation from an older prefix. Every assistant
turn in any such chain is genuine server output, so neither grants the
browser authority it was not given.

No Streamlit imports here.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from dataclasses import dataclass
from typing import List

from src.tradelens.api.config import service_secrets

GENESIS = "genesis"
MAX_TRANSCRIPT_TURNS = 40
TRANSCRIPT_TTL_SECONDS = 12 * 3600
CLOCK_SKEW_SECONDS = 60

_DOMAIN = b"tl.partner.transcript.v1"
_VERSION = 1
_ROLES = ("user", "assistant")
_CONV_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
_MODE_RE = re.compile(r"^(global|trade:[1-9][0-9]{0,17})$")
_MAC_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class TranscriptTurn:
    idx: int
    role: str
    text: str
    iat: int
    mac: str


class TranscriptInvalid(Exception):
    """One refusal for every failure. Which check failed is never returned."""

    def __init__(self) -> None:
        super().__init__("transcript_invalid")


def new_conversation_id() -> str:
    """A 128-bit, server-issued conversation id."""
    return secrets.token_urlsafe(16)


def _keys() -> List[bytes]:
    """One domain-separated MAC key per configured service secret.

    The raw secret is never the MAC key: a MAC made with it for any other
    purpose (request signing) can never verify as a transcript turn.
    Current secret first, so new turns are signed with it; the previous
    secret still verifies turns issued before a rotation.
    """
    configured = [s for s in service_secrets() if s]
    if not configured:
        raise RuntimeError("no service secret is configured")
    return [
        hmac.new(s.encode("utf-8"), _DOMAIN, hashlib.sha256).digest()
        for s in configured
    ]


def _digest(
    *,
    owner: int,
    conv: str,
    mode: str,
    idx: int,
    role: str,
    text: str,
    prev: str,
    iat: int,
) -> bytes:
    body = {
        "v": _VERSION,
        "owner": owner,
        "conv": conv,
        "mode": mode,
        "idx": idx,
        "role": role,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "prev": prev,
        "iat": iat,
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).digest()


def _mac(key: bytes, digest: bytes) -> str:
    return hmac.new(key, digest, hashlib.sha256).hexdigest()


def _valid_ids(owner: int, conv: str, mode: str) -> bool:
    return (
        isinstance(owner, int)
        and not isinstance(owner, bool)
        and owner > 0
        and isinstance(conv, str)
        and bool(_CONV_RE.match(conv))
        and isinstance(mode, str)
        and bool(_MODE_RE.match(mode))
    )


def sign_turn(
    *,
    owner: int,
    conv: str,
    mode: str,
    idx: int,
    role: str,
    text: str,
    prev_mac: str,
    iat: int,
) -> TranscriptTurn:
    """Sign one turn onto the chain whose head is ``prev_mac``."""
    if not _valid_ids(owner, conv, mode) or role not in _ROLES:
        raise ValueError("invalid transcript identity")
    digest = _digest(
        owner=owner,
        conv=conv,
        mode=mode,
        idx=idx,
        role=role,
        text=text,
        prev=prev_mac,
        iat=iat,
    )
    return TranscriptTurn(
        idx=idx, role=role, text=text, iat=iat, mac=_mac(_keys()[0], digest)
    )


def _field(turn, name):
    return getattr(turn, name) if isinstance(turn, TranscriptTurn) else turn.get(name)


def verify_transcript(turns, *, owner: int, conv: str, mode: str, now: int) -> list:
    """Recompute the chain from GENESIS; return role/content pairs or refuse.

    ``turns`` may be ``TranscriptTurn`` objects or plain dicts with exactly
    idx/role/text/iat/mac. A transcript is a run of COMPLETE exchanges: it
    has an even length and alternates user → assistant from index 0.
    """
    if not _valid_ids(owner, conv, mode) or not isinstance(turns, list):
        raise TranscriptInvalid()
    if len(turns) > MAX_TRANSCRIPT_TURNS or len(turns) % 2 != 0:
        raise TranscriptInvalid()
    keys = _keys()
    prev = GENESIS
    out = []
    for position, turn in enumerate(turns):
        if not isinstance(turn, (TranscriptTurn, dict)):
            raise TranscriptInvalid()
        if isinstance(turn, dict) and set(turn) != {
            "idx",
            "role",
            "text",
            "iat",
            "mac",
        }:
            raise TranscriptInvalid()
        idx, role = _field(turn, "idx"), _field(turn, "role")
        text, iat, mac = _field(turn, "text"), _field(turn, "iat"), _field(turn, "mac")
        if (
            isinstance(idx, bool)
            or not isinstance(idx, int)
            or idx != position
            or role != _ROLES[position % 2]
            or not isinstance(text, str)
            or isinstance(iat, bool)
            or not isinstance(iat, int)
            or not isinstance(mac, str)
            or not _MAC_RE.match(mac)
        ):
            raise TranscriptInvalid()
        if iat > now + CLOCK_SKEW_SECONDS or now - iat > TRANSCRIPT_TTL_SECONDS:
            raise TranscriptInvalid()
        digest = _digest(
            owner=owner,
            conv=conv,
            mode=mode,
            idx=idx,
            role=role,
            text=text,
            prev=prev,
            iat=iat,
        )
        verified = None
        for key in keys:
            expected = _mac(key, digest)
            if hmac.compare_digest(expected, mac):
                verified = expected
                break
        if verified is None:
            raise TranscriptInvalid()
        # Thread the MAC WE recomputed and verified — never the browser's.
        prev = verified
        out.append({"role": role, "content": text})
    return out


def chain_head(turns) -> str:
    """The MAC the next turn must chain onto (call only after verification)."""
    if not turns:
        return GENESIS
    return _field(turns[-1], "mac")


def turn_key(conv: str, position: int, client_turn_id: str) -> str:
    """The rate-limit/idempotency key for one turn: a digest, never text."""
    material = "partner|{}|{}|{}".format(conv, int(position), client_turn_id)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()
