"""The single gate every authenticated route goes through."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from src.tradelens.api.security import verify_signature
from src.tradelens.services.auth_sessions import restore_website_session_handle
from src.tradelens.services.corrections import corrections_scope

MAX_BODY_BYTES = 1_048_576


def _unauthorized() -> HTTPException:
    """One refusal for every failure. Callers learn nothing about which lock failed."""
    return HTTPException(status_code=401, detail="unauthenticated")


async def verified_body(request: Request) -> bytes:
    """Read the body once, enforce Lock 1 against it, and hand it on.

    Reading here rather than in the route matters: the signature covers these
    exact bytes, so verification must see what the handler will see.
    """
    declared = request.headers.get("content-length")
    if declared:
        try:
            if int(declared) > MAX_BODY_BYTES:
                raise HTTPException(status_code=413, detail="request too large")
        except ValueError:
            # A malformed or absent length cannot be trusted. The streaming cap
            # below is authoritative for both chunked and ordinary requests.
            pass

    chunks = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="request too large")
        chunks.append(chunk)
    body = b"".join(chunks)
    # Starlette's body() uses this cache. A future route may need the same bytes
    # after this dependency consumes the ASGI receive channel; it must never see
    # a different body from the one whose hash was verified.
    request._body = body
    if not verify_signature(
        request.headers.get("X-TL-Signature"),
        request.method,
        request.url.path,
        request.url.query,
        body,
    ):
        raise _unauthorized()
    return body


async def current_user(request: Request, _body: bytes = Depends(verified_body)):
    """Resolve the owner of this request, and scope correction memory to them.

    **The id comes from the session row and nowhere else.** No header, query
    parameter, or body field may name the account being acted on; that is how one
    authenticated user ends up reading another's journal. Everything downstream
    receives this value explicitly.

    Lock 1 has already run via the `verified_body` dependency, proving the caller
    is our own frontend. It says nothing about identity, which is why Lock 2
    below is resolved against the database rather than trusted from upstream.

    Yields inside `corrections_scope` so the ContextVar is reset even when the
    handler raises. FastAPI reuses threadpool workers, and a value left behind is
    one the next request on that thread can read.
    """
    user_id = restore_website_session_handle(request.headers.get("X-TL-Session-Handle"))
    if user_id is None:
        raise _unauthorized()
    with corrections_scope(user_id):
        yield user_id
