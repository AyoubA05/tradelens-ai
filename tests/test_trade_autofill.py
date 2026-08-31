"""The autofill suggestion service: allowlist, cost order, and draft-only writes.

The properties under test are the ones a reviewer cannot see by reading the
happy path:

* a field the model invents has nowhere to go — the allowlist filters the
  model's output *before* anything is stored;
* a server-derived field is dropped even when the model volunteers it;
* `Usage` is recorded the instant the provider returns, so a response that
  then fails validation is still billed-and-visible;
* no number of autofill runs creates a `trades` row.
"""

from __future__ import annotations

import pytest

from src.tradelens.api.schemas.trades import (
    CREATABLE_TRADE_FIELDS,
    SERVER_OWNED_ON_CREATE,
    TradeDraftPayload,
)
from src.tradelens.db.models import Trade
from src.tradelens.db.session import SessionLocal
from src.tradelens.services import drafts, trade_autofill
from src.tradelens.services.trade_autofill import (
    AUTOFILL_SUGGESTION_FIELDS,
    AUTOFILL_TRADE_FIELDS,
    build_suggestions,
    filter_suggestions,
    save_suggestions_to_draft,
)


def _analysis(**overlay):
    return {
        "descriptive": {
            "detected_asset": "NQ",
            "detected_timeframe": "15m",
            "htf_bias": "bullish",
            "bias": "bullish",
            "liquidity_sweep": True,
        },
        "trade_overlay": {
            "source": "visible_trade_box",
            "direction": "long",
            "entry_price": 20100.25,
            "stop_price": 20080.0,
            "confidence": {"entry_price": 0.91, "stop_price": 0.88},
            **overlay,
        },
    }


# ------------------------------------------------------------- the allowlist


def test_autofill_allowlist_is_a_subset_of_the_create_allowlist():
    assert AUTOFILL_TRADE_FIELDS <= CREATABLE_TRADE_FIELDS


def test_autofill_allowlist_is_disjoint_from_server_owned_fields():
    assert AUTOFILL_TRADE_FIELDS.isdisjoint(SERVER_OWNED_ON_CREATE)


def test_autofill_allowlist_is_writable_on_a_draft():
    # Suggestions land on the draft, so every suggestable field must be a
    # field the draft contract itself accepts.
    assert AUTOFILL_SUGGESTION_FIELDS <= frozenset(TradeDraftPayload.model_fields)


def test_a_field_the_model_invents_is_dropped():
    kept = filter_suggestions(
        {
            "entry_price": {"value": 1.0, "confidence": 0.9},
            "wire_me_money": {"value": "yes", "confidence": 1.0},
        }
    )
    assert "wire_me_money" not in kept
    assert "entry_price" in kept


@pytest.mark.parametrize(
    "derived",
    [
        "session",
        "killzone",
        "strategy_used",
        "asset_class",
        "rr_planned",
        "day_of_week",
        "trade_hash",
        "create_idempotency_key",
        "user_id",
        "id",
    ],
)
def test_a_derived_field_is_dropped(derived):
    kept = filter_suggestions({derived: {"value": "NY AM", "confidence": 1.0}})
    assert kept == {}


def test_the_filter_runs_before_anything_is_stored(website_session_handle):
    user_id, _ = website_session_handle
    save_suggestions_to_draft(
        user_id, {"session": {"value": "NY AM"}, "asset": {"value": "NQ"}}
    )
    stored = drafts.get_draft(user_id)["ai_suggestions"]
    assert "session" not in stored
    assert stored["asset"]["value"] == "NQ"


def test_build_suggestions_drops_a_derived_field_the_model_volunteers():
    analysis = _analysis()
    analysis["descriptive"]["session"] = "NY AM"
    analysis["descriptive"]["killzone"] = "New York AM"
    built = build_suggestions(analysis)
    assert "session" not in built and "killzone" not in built
    assert built["entry_price"]["value"] == 20100.25


def test_build_suggestions_carries_confidence_and_the_shared_autocheck_policy():
    built = build_suggestions(_analysis())
    assert built["entry_price"]["confidence"] == 0.91
    # 0.91 >= AUTOCHECK_MIN_CONFIDENCE and entry_price is an autocheck field.
    assert built["entry_price"]["autocheck"] is True
    # tp_price is never auto-checked whatever the confidence.
    built = build_suggestions(
        _analysis(tp_price=20200.0, confidence={"tp_price": 0.99})
    )
    assert built["tp_price"]["autocheck"] is False


# ------------------------------------------------------ draft, never `trades`


def _trades_row_count() -> int:
    db = SessionLocal()
    try:
        return db.query(Trade).count()
    finally:
        db.close()


def test_no_number_of_autofill_runs_creates_a_trades_row(website_session_handle):
    user_id, _ = website_session_handle
    before = _trades_row_count()
    for _ in range(5):
        save_suggestions_to_draft(user_id, build_suggestions(_analysis()))
    assert _trades_row_count() == before == 0


def test_suggestions_do_not_overwrite_the_trader_s_own_draft_values(
    website_session_handle,
):
    user_id, _ = website_session_handle
    drafts.save_draft(user_id, {"asset": "MNQ", "notes": "mine"})
    save_suggestions_to_draft(user_id, build_suggestions(_analysis()))
    draft = drafts.get_draft(user_id)
    # The suggestion is provenance-tagged metadata; the trader's own values are
    # what the form shows until they accept one.
    assert draft["asset"] == "MNQ"
    assert draft["notes"] == "mine"
    assert draft["ai_suggestions"]["asset"]["value"] == "NQ"


def test_a_saved_suggestion_set_survives_the_draft_contract(website_session_handle):
    # `GET /v1/trades/draft` re-validates the stored payload through
    # `TradeDraftPayload`, which forbids extras — a suggestion shape it cannot
    # parse would turn every subsequent draft read into a 500.
    user_id, _ = website_session_handle
    save_suggestions_to_draft(user_id, build_suggestions(_analysis()))
    TradeDraftPayload(**drafts.get_draft(user_id))


# --------------------------------------------------------- cost, before parse


def test_usage_is_recorded_even_when_validation_then_fails(monkeypatch, tmp_path):
    """A billed call that returns junk must still appear in cost tracking."""
    recorded = []

    class _Boom(Exception):
        pass

    def _analyzer(image_path, trade_ctx, strategy_profile=None, on_usage=None):
        if on_usage is not None:
            on_usage("usage-object")
        raise _Boom("unparseable response")

    monkeypatch.setattr(trade_autofill, "analyze_screenshot_v3", _analyzer)
    monkeypatch.setattr(trade_autofill, "check_screenshot_quality", lambda p: _Usable())
    image = tmp_path / "chart.png"
    image.write_bytes(b"x")

    with pytest.raises(_Boom):
        trade_autofill.analyse_image(image, on_usage=recorded.append)
    assert recorded == ["usage-object"]


class _Usable:
    usable = True
    warnings = []


def test_an_unusable_image_never_reaches_the_provider(monkeypatch, tmp_path):
    calls = []

    class _Unusable:
        usable = False
        warnings = ["The image file is missing or empty."]

    monkeypatch.setattr(
        trade_autofill, "check_screenshot_quality", lambda p: _Unusable()
    )
    monkeypatch.setattr(
        trade_autofill,
        "analyze_screenshot_v3",
        lambda *a, **k: calls.append(1),
    )
    image = tmp_path / "chart.png"
    image.write_bytes(b"x")
    with pytest.raises(trade_autofill.AutofillUnavailable):
        trade_autofill.analyse_image(image, on_usage=lambda u: None)
    assert calls == []


def test_analyze_screenshot_v3_records_usage_before_it_parses(monkeypatch, tmp_path):
    """The ordering pinned inside the provider call itself, not around it.

    Stubbing the analyzer out (as the test above does) proves the callback is
    plumbed through; it cannot prove the callback fires before parsing. This
    drives the real function with an unparseable body: a mutation that moves
    the `on_usage` call below `parse_ai_json` loses the record here.
    """
    from src.tradelens.services import vision as vision_module

    recorded = []
    monkeypatch.setattr(
        vision_module, "vision", lambda **kwargs: ("definitely not json", "usage")
    )
    monkeypatch.setattr(vision_module, "load_prompt", lambda name: "system")
    image = tmp_path / "chart.png"
    image.write_bytes(b"x")

    with pytest.raises(Exception):
        vision_module.analyze_screenshot_v3(image, {}, None, on_usage=recorded.append)
    assert recorded == ["usage"]


def test_analyze_screenshot_v3_records_usage_when_the_provider_is_unavailable(
    monkeypatch, tmp_path
):
    """An `AIUnavailable` body can still be a billed round trip."""
    from src.tradelens.services import vision as vision_module
    from src.tradelens.services.ai_client import AIUnavailable

    recorded = []
    monkeypatch.setattr(
        vision_module,
        "vision",
        lambda **kwargs: (AIUnavailable(reason="provider said no"), "usage"),
    )
    monkeypatch.setattr(vision_module, "load_prompt", lambda name: "system")
    image = tmp_path / "chart.png"
    image.write_bytes(b"x")

    with pytest.raises(vision_module.ScreenshotAnalysisError):
        vision_module.analyze_screenshot_v3(image, {}, None, on_usage=recorded.append)
    assert recorded == ["usage"]


# ------------------------------------- the FINALIZED image, never an upload


def _screenshot_row(user_id: int, file_path_for) -> int:
    """One screenshot row whose `file_path` is chosen by the caller."""
    from datetime import datetime, timezone

    from src.tradelens.db.models import Screenshot
    from src.tradelens.services import trade_service

    trade = trade_service.create_trade(
        {"asset": "NQ", "trade_date": "2026-08-10"}, user_id=user_id
    )
    db = SessionLocal()
    try:
        row = Screenshot(
            trade_id=trade.id,
            file_path=file_path_for(user_id, trade.id),
            uploaded_at=datetime.now(timezone.utc).isoformat(),
        )
        db.add(row)
        db.commit()
        return int(row.id)
    finally:
        db.close()


class _NeverCalledS3:
    def get_object(self, **kwargs):  # pragma: no cover — the point is it isn't
        raise AssertionError(f"read an object it should have refused: {kwargs}")


def test_a_quarantine_key_is_never_read_for_analysis(
    website_session_handle, monkeypatch
):
    """The one property autofill's safety rests on.

    A quarantine object holds the bytes the *client* sent — not decoded, not
    capped, not re-encoded. `finalize_upload` is what turns those into bytes we
    produced, and analysing anything else would hand a crafted container
    straight to the model. A row pointing at a quarantine key must therefore
    read as "no such screenshot", not as an image.
    """
    from src.tradelens.api import storage

    user_id, _ = website_session_handle
    screenshot_id = _screenshot_row(
        user_id,
        lambda u, t: f"quarantine/u/{u}/t/{t}/"
        "00000000-0000-4000-8000-000000000000.png",
    )
    monkeypatch.setattr(storage, "_client", lambda: _NeverCalledS3())

    assert storage.read_owned_final_object(user_id, screenshot_id) is None


def test_a_key_naming_another_tenant_is_never_read(website_session_handle, monkeypatch):
    """A corrupted `file_path` must not become a cross-tenant read."""
    from src.tradelens.api import storage

    user_id, _ = website_session_handle
    screenshot_id = _screenshot_row(
        user_id,
        lambda u, t: f"u/{u + 1}/t/{t}/00000000-0000-4000-8000-000000000000.png",
    )
    monkeypatch.setattr(storage, "_client", lambda: _NeverCalledS3())

    assert storage.read_owned_final_object(user_id, screenshot_id) is None


def test_an_unreadable_screenshot_never_reaches_the_provider(
    website_session_handle, monkeypatch
):
    """`suggest_from_screenshot` refuses before any billable call."""
    from src.tradelens.api import storage

    user_id, _ = website_session_handle
    calls = []
    monkeypatch.setattr(storage, "read_owned_final_object", lambda u, s: None)
    monkeypatch.setattr(
        trade_autofill, "analyze_screenshot_v3", lambda *a, **k: calls.append(1)
    )
    with pytest.raises(trade_autofill.AutofillUnavailable):
        trade_autofill.suggest_from_screenshot(user_id, 1, on_usage=lambda u: None)
    assert calls == []


def test_trade_autofill_imports_without_loading_streamlit():
    """services/trade_autofill.py must not drag Streamlit into a service process.

    `services/` is imported by the FastAPI container, which has no business
    carrying a Streamlit runtime dependency. A same-process `sys.modules`
    check would lie here: pytest's own conftest imports Streamlit (for
    AppTest fixtures) before this test ever runs, and importing it earlier
    in this repo would too. A fresh subprocess is the only check that can't
    pass by accident — it starts with an empty `sys.modules` and fails loudly
    if anything on the way to `trade_autofill` reaches into `ui/components`
    (or any other Streamlit-importing module) again.
    """
    import subprocess
    import sys
    from pathlib import Path

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import src.tradelens.services.trade_autofill; "
            "sys.exit(1 if 'streamlit' in sys.modules else 0)",
        ],
        cwd=str(Path(__file__).resolve().parent.parent),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "importing src.tradelens.services.trade_autofill loaded Streamlit "
        f"(stdout={result.stdout!r} stderr={result.stderr!r})"
    )
