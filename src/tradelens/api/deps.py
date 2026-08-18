"""The single gate every authenticated route goes through."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from src.tradelens.api.security import verify_signature
from src.tradelens.services.auth_sessions import restore_website_session
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
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="request too large")
    if not verify_signature(
        request.headers.get("X-TL-Signature"),
        request.method,
        request.url.path,
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
    user_id = restore_website_session(request.headers.get("X-TL-Session"))
    if user_id is None:
        raise _unauthorized()
    with corrections_scope(user_id):
        yield user_id
