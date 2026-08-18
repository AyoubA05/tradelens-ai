"""Lock 1 — proof that a request came from our own frontend.

The signed message binds the timestamp, method, path, canonical query and a
hash of the body:

    {timestamp}.{METHOD}.{path}.{canonical_query}.{sha256(body)}

Binding each of those is what makes a captured header useless anywhere else. A
signature over the timestamp alone would be a reusable bearer token for every
endpoint on the service, which is the mistake this shape exists to avoid.

**Why the query is in here.** It was not, originally, and the endpoint that
existed at the time ignored query parameters for authorization — so nothing was
exploitable. But that made the contract depend on a property of the handlers
rather than of the signature, and the first endpoint to read a filter, a date
range, or a page cursor from the query string would have silently inherited an
unauthenticated input. Binding it now is cheap; retrofitting it after such an
endpoint exists means changing an auth contract in production.

**Canonical, not raw.** The query is normalised before signing: each name and
value is RFC 3986 percent-encoded, then pairs are sorted by name and then value.
Signing the raw string would mean `?a=1&b=2` and `?b=2&a=1` — the same request
by every semantic that matters — produced different signatures, so any layer
that reordered or re-encoded parameters between signer and verifier would break
authentication rather than merely fail to help it.

This proves *which caller*. It proves nothing about *which user* — that is
Lock 2's job, and neither lock is sufficient alone.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Optional
from urllib.parse import parse_qsl, quote

from src.tradelens.api.config import service_secrets

REPLAY_WINDOW_SECONDS = 60

# RFC 3986 unreserved characters. Everything else is percent-encoded, including
# the sub-delims that `quote` leaves alone by default, so the two languages
# cannot disagree about a character neither of them thought worth escaping.
_UNRESERVED = "-._~"


def canonical_query(query: str) -> str:
    """Normalise a raw query string into the form that gets signed.

    Blank values are kept: `?debug=` and `?debug` are inputs a handler can read,
    so dropping them would leave a signed request whose meaning differed from
    the one that was verified.
    """
    if not query:
        return ""
    # A leading "?" is not part of the query. `URLSearchParams` strips it and
    # `parse_qsl` does not, so without this the two implementations disagreed
    # on every query a caller happened to pass with its delimiter attached —
    # the signer producing one signature and the verifier expecting another,
    # surfacing as an unexplainable 401 rather than as an obvious bug. Found by
    # the differential corpus in scripts/generate_canonical_query_cases.py.
    if query.startswith("?"):
        query = query[1:]
    pairs = [
        (quote(name, safe=_UNRESERVED), quote(value, safe=_UNRESERVED))
        for name, value in parse_qsl(query, keep_blank_values=True)
    ]
    pairs.sort()
    return "&".join(f"{name}={value}" for name, value in pairs)


def build_message(
    timestamp: str, method: str, path: str, query: str, body: bytes
) -> str:
    return ".".join(
        (
            timestamp,
            method.upper(),
            path,
            canonical_query(query),
            hashlib.sha256(body).hexdigest(),
        )
    )


def sign_request(
    secret: str, timestamp: str, method: str, path: str, query: str, body: bytes
) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        build_message(timestamp, method, path, query, body).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_signature(
    header: Optional[str],
    method: str,
    path: str,
    query: str,
    body: bytes,
    now: Optional[float] = None,
) -> bool:
    """Whether ``header`` is a valid, fresh signature. Never raises.

    Returns False for every failure mode — absent, malformed, stale, or wrong —
    so a caller cannot learn which check it failed.
    """
    secrets = service_secrets()
    if not header or not secrets:
        return False
    if not header.startswith("v1="):
        return False

    try:
        timestamp, provided = header[3:].split(":", 1)
        age = abs((now if now is not None else time.time()) - int(timestamp))
    except (ValueError, TypeError):
        return False

    if age > REPLAY_WINDOW_SECONDS:
        return False

    # Every accepted secret is compared, without short-circuiting on the first
    # match, so how long this takes does not reveal which secret was used.
    matched = False
    for secret in secrets:
        expected = sign_request(secret, timestamp, method, path, query, body)
        if hmac.compare_digest(expected, provided):
            matched = True
    return matched
