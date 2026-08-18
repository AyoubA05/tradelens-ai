"""Lock 1 — proof that a request came from our own frontend.

The signed message binds the timestamp, method, path and a hash of the body:

    {timestamp}.{METHOD}.{path}.{sha256(body)}

Binding the path and body is what makes a captured header useless elsewhere. A
signature over the timestamp alone would be a reusable bearer token for every
endpoint on the service, which is the mistake this shape exists to avoid.

This proves *which caller*. It proves nothing about *which user* — that is
Lock 2's job, and neither lock is sufficient alone.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Optional

from src.tradelens.api.config import service_secrets

REPLAY_WINDOW_SECONDS = 60


def build_message(timestamp: str, method: str, path: str, body: bytes) -> str:
    return f"{timestamp}.{method.upper()}.{path}.{hashlib.sha256(body).hexdigest()}"


def sign_request(
    secret: str, timestamp: str, method: str, path: str, body: bytes
) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        build_message(timestamp, method, path, body).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_signature(
    header: Optional[str],
    method: str,
    path: str,
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
        expected = sign_request(secret, timestamp, method, path, body)
        if hmac.compare_digest(expected, provided):
            matched = True
    return matched
