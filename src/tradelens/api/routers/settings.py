"""`/v1/settings` — preferences, data tools and account controls.

An owner-singleton: no route takes an id, and no request body names an owner,
a trade, a file or an object key. The owner is the session.

Status mapping, fixed and never carrying exception or driver text:

* 422 — a field problem by field and fixed code (`timezone`/`unsupported`,
  `csv`/`too_many_rows`), or a schema refusal (`type`/`loc`/`msg` only). A
  wrong typed confirmation is a schema refusal: the `Literal` is the check.
* 503 `screenshot_cleanup_failed` — a deletion could not remove every owned
  stored screenshot, so **nothing was deleted**. `remaining` (a retry can
  clear it) and `unresolvable` (it cannot) are reported separately, exactly
  as the single-trade delete does.
* 404 — account deletion for an account that no longer exists.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import JSONResponse

from src.tradelens.api.deps import current_user
from src.tradelens.api.schemas.settings import (
    CsvExportResponse,
    CsvImportResponse,
    CsvImportWrite,
    DeleteAccountWrite,
    DeleteTradesResponse,
    DeleteTradesWrite,
    SampleTradesResponse,
    SettingsAccount,
    SettingsAI,
    SettingsCost,
    SettingsCostRow,
    SettingsData,
    SettingsResponse,
    SettingsTimezone,
    TimezoneWrite,
)
from src.tradelens.api.schemas.trades import ScreenshotCleanupFailedResponse
from src.tradelens.db.models import Trade
from src.tradelens.db.session import SessionLocal
from src.tradelens.services import csvio
from src.tradelens.services.ai_client import has_api_key
from src.tradelens.services.app_settings import (
    TIMEZONE_OPTIONS,
    get_timezone,
    set_timezone,
    today_for_owner,
)
from src.tradelens.services.cost import monthly_cost_by_feature
from src.tradelens.services.data_deletion import (
    ScreenshotCleanupBlocked,
    delete_account_and_objects,
    delete_all_trades_and_objects,
)
from src.tradelens.services.demo import is_demo
from src.tradelens.services.password_reset import email_configured
from src.tradelens.services.sample_data import (
    clear_sample_trades,
    count_sample_trades,
    load_sample_trades,
)
from src.tradelens.services.trade_service import get_trades
from src.tradelens.services.users import get_user_by_id

router = APIRouter(prefix="/v1/settings", tags=["settings"])

# The service returns one fixed sentence per bad row; a hostile file with
# thousands of bad rows must not become a megabyte of response.
_MAX_IMPORT_ERRORS = 20


def _trade_count(owner: int) -> int:
    db = SessionLocal()
    try:
        return db.query(Trade).filter(Trade.user_id == owner).count()
    finally:
        db.close()


def _ai_state() -> str:
    """Decision S2: availability only — never how a key is configured."""
    if has_api_key():
        return "enabled"
    if is_demo():
        return "demo"
    return "unavailable"


def _response(owner: int) -> SettingsResponse:
    user = get_user_by_id(owner)
    today = today_for_owner(owner)
    frame = monthly_cost_by_feature(today.year, today.month, user_id=owner)
    rows = [
        SettingsCostRow(
            feature=str(row["feature"]),
            cost_usd=round(float(row["cost_usd"]), 6),
            calls=int(row["calls"]),
        )
        for row in frame.to_dict("records")
    ]
    return SettingsResponse(
        account=SettingsAccount(
            username=str(getattr(user, "username", "") or ""),
            email=getattr(user, "email", None),
            email_verified=getattr(user, "email_verified_at", None) is not None,
        ),
        timezone=SettingsTimezone(
            current=get_timezone(owner), options=list(TIMEZONE_OPTIONS)
        ),
        ai=SettingsAI(state=_ai_state()),
        data=SettingsData(
            trade_count=_trade_count(owner),
            sample_count=count_sample_trades(owner),
            csv_columns=list(csvio.CSV_COLUMNS),
            max_import_rows=csvio.MAX_IMPORT_ROWS,
        ),
        cost=SettingsCost(
            month="{:04d}-{:02d}".format(today.year, today.month),
            total_usd=round(sum(row.cost_usd for row in rows), 6),
            rows=rows,
        ),
        reset_email_configured=bool(email_configured()),
        demo_mode=bool(is_demo()),
    )


def _field_problem(field: str, problem: str) -> JSONResponse:
    return JSONResponse(
        status_code=422, content={"detail": [{"field": field, "problem": problem}]}
    )


def _cleanup_failed(outcome) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "error": "screenshot_cleanup_failed",
            "remaining": outcome.remaining,
            "unresolvable": outcome.unresolvable,
        },
    )


@router.get("", response_model=SettingsResponse)
def read_settings(user_id: int = Depends(current_user)):
    return _response(user_id)


@router.put("/timezone", response_model=SettingsResponse, responses={422: {}})
def write_timezone(payload: TimezoneWrite, user_id: int = Depends(current_user)):
    try:
        set_timezone(user_id, payload.timezone)
    except ValueError:
        return _field_problem("timezone", "unsupported")
    return _response(user_id)


@router.post(
    "/sample-trades",
    response_model=SampleTradesResponse,
    responses={503: {"model": ScreenshotCleanupFailedResponse}},
)
def load_samples(user_id: int = Depends(current_user)):
    try:
        count = load_sample_trades(user_id)
    except ScreenshotCleanupBlocked as exc:
        raise _cleanup_failed(exc.outcome)
    return SampleTradesResponse(count=count, sample_count=count_sample_trades(user_id))


@router.delete(
    "/sample-trades",
    response_model=SampleTradesResponse,
    responses={503: {"model": ScreenshotCleanupFailedResponse}},
)
def clear_samples(user_id: int = Depends(current_user)):
    try:
        count = clear_sample_trades(user_id)
    except ScreenshotCleanupBlocked as exc:
        raise _cleanup_failed(exc.outcome)
    return SampleTradesResponse(count=count, sample_count=count_sample_trades(user_id))


@router.get("/export", response_model=CsvExportResponse)
def export_csv(user_id: int = Depends(current_user)):
    import pandas as pd

    trades = get_trades(user_id=user_id)
    frame = pd.DataFrame(
        [{col: getattr(t, col, None) for col in csvio.CSV_COLUMNS} for t in trades]
    )
    return CsvExportResponse(
        filename="trades.csv",
        row_count=len(trades),
        csv=csvio.export_trades_csv(frame).decode("utf-8"),
    )


@router.post("/import", response_model=CsvImportResponse, responses={422: {}})
def import_csv(payload: CsvImportWrite, user_id: int = Depends(current_user)):
    try:
        inserted, skipped, errors = csvio.import_trades_csv_text(payload.csv, user_id)
    except csvio.TooManyRows:
        return _field_problem("csv", "too_many_rows")
    return CsvImportResponse(
        inserted=inserted, skipped=skipped, errors=errors[:_MAX_IMPORT_ERRORS]
    )


@router.post(
    "/delete-trades",
    response_model=DeleteTradesResponse,
    responses={503: {"model": ScreenshotCleanupFailedResponse}},
)
def delete_trades(payload: DeleteTradesWrite, user_id: int = Depends(current_user)):
    del payload  # the Literal already verified the typed confirmation
    outcome = delete_all_trades_and_objects(user_id)
    if outcome.blocked:
        raise _cleanup_failed(outcome)
    return DeleteTradesResponse(deleted=outcome.deleted)


@router.post(
    "/delete-account",
    status_code=204,
    responses={404: {}, 503: {"model": ScreenshotCleanupFailedResponse}},
)
def delete_my_account(
    payload: DeleteAccountWrite, user_id: int = Depends(current_user)
):
    del payload  # the Literal already verified the typed confirmation
    outcome = delete_account_and_objects(user_id)
    if outcome.blocked:
        raise _cleanup_failed(outcome)
    if not outcome.deleted:
        raise HTTPException(status_code=404, detail="Not Found")
    return Response(status_code=204)
