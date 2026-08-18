"""Owner checks missed by the first Phase 0 tenant-isolation pass."""

from types import SimpleNamespace

import pytest

from src.tradelens.db.models import AIAnalysis, Screenshot
from src.tradelens.db.session import SessionLocal
from src.tradelens.services import (
    ai_analysis_service,
    corrections,
    metrics_store,
    screenshot_service,
    trade_service,
)


def _trade(owner, asset="NQ"):
    return {
        "user_id": owner,
        "trade_date": "2026-08-12",
        "asset": asset,
        "result": "Win",
        "pnl": 1.0,
    }


def _analysis_for(trade_id):
    db = SessionLocal()
    try:
        row = AIAnalysis(trade_id=trade_id, bias="Long")
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id
    finally:
        db.close()


def test_create_trade_requires_authenticated_owner_and_ignores_payload_owner(two_users):
    a, b = two_users
    with pytest.raises(TypeError):
        trade_service.create_trade(_trade(b))

    created = trade_service.create_trade(_trade(b), user_id=a)
    assert created.user_id == a


def test_ai_analysis_reads_and_updates_require_trade_ownership(two_users):
    a, b = two_users
    theirs = trade_service.create_trade(_trade(b), user_id=b)
    analysis_id = _analysis_for(theirs.id)

    assert ai_analysis_service.get_analysis_for_trade(theirs.id, user_id=a) is None
    with pytest.raises(ValueError):
        ai_analysis_service.update_analysis_fields(analysis_id, user_id=a, bias="Short")
    with pytest.raises(ValueError):
        ai_analysis_service.save_grade(analysis_id, {"grade": "A"}, user_id=a)
    with pytest.raises(ValueError):
        ai_analysis_service.save_journal(analysis_id, "private", user_id=a)
    with pytest.raises(ValueError):
        ai_analysis_service.save_user_grade(theirs.id, "A", user_id=a)
    with pytest.raises(ValueError):
        ai_analysis_service.save_trade_smc(theirs.id, user_id=a, htf_bias="Short")


def test_analysis_creation_cannot_attach_spend_to_another_users_trade(two_users):
    a, b = two_users
    theirs = trade_service.create_trade(_trade(b), user_id=b)
    usage = SimpleNamespace(
        model="m", tokens_in=1, tokens_out=1, estimated_cost_usd=0.1
    )

    with pytest.raises(ValueError):
        ai_analysis_service.create_or_update_analysis(
            theirs.id, {"bias": "Long"}, usage, user_id=a
        )


def test_screenshot_persistence_and_lookup_require_trade_ownership(
    two_users, tmp_path, monkeypatch
):
    a, b = two_users
    theirs = trade_service.create_trade(_trade(b), user_id=b)
    monkeypatch.setattr(screenshot_service, "SCREENSHOTS_DIR", tmp_path)
    upload = SimpleNamespace(name="x.png", read=lambda: b"not-used")

    with pytest.raises(PermissionError):
        screenshot_service.save_screenshot(theirs.id, upload, user_id=a)
    with pytest.raises(PermissionError):
        screenshot_service.save_screenshot_url(
            theirs.id, "https://example.test/x.png", user_id=a
        )

    db = SessionLocal()
    try:
        db.add(Screenshot(trade_id=theirs.id, file_path="private.png"))
        db.commit()
    finally:
        db.close()
    assert trade_service.get_primary_screenshot(theirs.id, user_id=a) is None


def test_correction_cannot_reference_another_users_trade_or_analysis(two_users):
    a, b = two_users
    theirs = trade_service.create_trade(_trade(b), user_id=b)
    analysis_id = _analysis_for(theirs.id)

    with pytest.raises(ValueError):
        corrections.record_correction(
            theirs.id,
            analysis_id,
            "bias",
            "Long",
            "Short",
            user_id=a,
        )


def test_metrics_timestamp_has_no_user_one_default():
    with pytest.raises(TypeError):
        metrics_store.get_computed_at()
    with pytest.raises(ValueError):
        metrics_store.get_computed_at(None)
