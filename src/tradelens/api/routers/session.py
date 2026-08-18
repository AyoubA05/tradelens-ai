"""Session introspection. The one endpoint Phase 0 needs."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.tradelens.api.deps import current_user

router = APIRouter(prefix="/v1/session", tags=["session"])


class WhoAmI(BaseModel):
    user_id: int


@router.get("/whoami")
def whoami(user_id: int = Depends(current_user)) -> WhoAmI:
    """Echo the authenticated owner.

    Exists to prove both locks end to end. The value returned is the one the
    session row resolved to, never anything the caller supplied.
    """
    return WhoAmI(user_id=user_id)
