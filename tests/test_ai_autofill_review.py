"""
AI Autofill Review wiring (Session F, Phase 2).

Non-visual logic for the screenshot-first New Trade panel: the pure mapping from
accepted AI suggestions to nt_* session-state writes, and the analyze→map wire.
Streamlit rendering itself is covered by the page boot smoke tests.
"""

import src.tradelens.ui.components.ai_autofill_review as comp
from src.tradelens.services.ai_overlay import TradeOverlay
from src.tradelens.services.assets import OTHER
from src.tradelens.ui.components.ai_autofill_review import build_form_writes

# ---------------------------------------------------------------------------
# build_form_writes — accepted suggestions -> nt_* session-state writes
# ---------------------------------------------------------------------------


def test_build_writes_known_asset_uses_dropdown_option():
    w = build_form_writes({"asset": "NQ"}, ["asset"], known_assets=["NQ", "ES"])
    assert w == {"nt_asset_select": "NQ"}


def test_build_writes_custom_asset_routes_to_other_plus_custom():
    w = build_form_writes({"asset": "TSLA"}, ["asset"], known_assets=["NQ", "ES"])
    assert w == {"nt_asset_select": OTHER, "nt_asset_custom": "TSLA"}


def test_build_writes_maps_timeframe_and_bias():
    w = build_form_writes(
        {"timeframe": "15m", "htf_bias": "Bullish", "ltf_bias": "Bearish"},
        ["timeframe", "htf_bias", "ltf_bias"],
    )
    assert w == {"nt_timeframe": "15m", "nt_htf": "Bullish", "nt_ltf": "Bearish"}


def test_build_writes_maps_confluences():
    w = build_form_writes({"confluences": ["FVG", "BOS"]}, ["confluences"])
    assert w == {"nt_confluences": ["FVG", "BOS"]}


def test_build_writes_only_includes_selected_fields():
    w = build_form_writes(
        {"asset": "NQ", "timeframe": "15m"}, ["timeframe"], known_assets=["NQ"]
    )
    assert w == {"nt_timeframe": "15m"}


def test_build_writes_skips_missing_and_none_values():
    assert build_form_writes({}, ["timeframe", "htf_bias"]) == {}
    assert build_form_writes({"timeframe": None}, ["timeframe"]) == {}


def test_build_writes_preserves_exact_option_string_on_normalized_match():
    # AI may give an unslashed/lowercased symbol; the dropdown write must still be
    # a real option string from known_assets, or the selectbox would raise.
    w = build_form_writes({"asset": "gbpusd"}, ["asset"], known_assets=["GBPUSD"])
    assert w == {"nt_asset_select": "GBPUSD"}


def test_build_writes_empty_asset_is_skipped():
    assert build_form_writes({"asset": ""}, ["asset"], known_assets=["NQ"]) == {}


def test_build_writes_custom_when_no_known_assets():
    w = build_form_writes({"asset": "NQ"}, ["asset"], known_assets=[])
    assert w == {"nt_asset_select": OTHER, "nt_asset_custom": "NQ"}


# ---------------------------------------------------------------------------
# run_autofill — analyze_source(...) -> map_analysis_to_form(...)
# ---------------------------------------------------------------------------


def test_run_autofill_wires_analyze_and_map(monkeypatch):
    captured = {}

    def fake_analyze(source, ctx, profile=None, analyzer=None):
        captured["source"] = source
        captured["ctx"] = ctx
        captured["profile"] = profile
        return {"bias": "bullish", "detected_timeframe": "15m"}, "USAGE"

    monkeypatch.setattr(comp, "analyze_source", fake_analyze)

    result, overlay, raw, usage = comp.run_autofill(
        "/tmp/x.png", {"name": "S"}, known_assets=["NQ"]
    )

    assert raw == {"bias": "bullish", "detected_timeframe": "15m"}
    assert usage == "USAGE"
    assert result.prefill["ltf_bias"] == "Bullish"
    assert result.prefill["timeframe"] == "15m"
    assert overlay.source == "none"  # flat descriptive dict carries no overlay
    assert overlay.has_prices() is False
    assert captured["source"] == "/tmp/x.png"
    assert captured["profile"] == {"name": "S"}


def test_run_autofill_passes_known_assets_for_in_list_flag(monkeypatch):
    monkeypatch.setattr(
        comp,
        "analyze_source",
        lambda s, c, p=None, analyzer=None: ({"detected_asset": "NQ"}, "U"),
    )
    result, _overlay, _raw, _usage = comp.run_autofill(
        "/tmp/x.png", {}, known_assets=["NQ", "ES"]
    )
    assert result.asset_in_list is True
    assert result.prefill["asset"] == "NQ"


def test_run_autofill_extracts_descriptive_and_overlay_from_v3(monkeypatch):
    v3 = {
        "descriptive": {"bias": "bearish", "detected_timeframe": "15m"},
        "trade_overlay": {
            "direction": "short",
            "entry_price": 100.0,
            "stop_price": 105.0,
            "confidence": {"entry_price": 0.7, "stop_price": 0.6},
            "source": "visible_trade_box",
        },
    }
    monkeypatch.setattr(
        comp, "analyze_source", lambda s, c, p=None, analyzer=None: (v3, "U")
    )
    result, overlay, raw, _usage = comp.run_autofill("/tmp/x.png", {}, known_assets=[])
    assert result.prefill["ltf_bias"] == "Bearish"  # descriptive feeds Phase 1
    assert overlay.entry_price == 100.0
    assert overlay.direction == "short"  # parsed but display-only
    assert raw is v3  # full v3 raw is returned for save-time persistence


# ---------------------------------------------------------------------------
# build_overlay_writes — accepted overlay prices -> nt_* writes (no direction)
# ---------------------------------------------------------------------------


def test_build_overlay_writes_maps_selected_prices():
    ov = TradeOverlay(entry_price=100.0, stop_price=95.0, source="visible_trade_box")
    w = comp.build_overlay_writes(ov, ["entry_price", "stop_price"])
    assert w == {"nt_entry": 100.0, "nt_stop": 95.0}


def test_build_overlay_writes_only_selected():
    ov = TradeOverlay(entry_price=100.0, stop_price=95.0, tp_price=110.0)
    w = comp.build_overlay_writes(ov, ["tp_price"])
    assert w == {"nt_tp": 110.0}


def test_build_overlay_writes_skips_none_prices():
    ov = TradeOverlay(entry_price=None, exit_price=110.0)
    w = comp.build_overlay_writes(ov, ["entry_price", "exit_price"])
    assert w == {"nt_exit": 110.0}


def test_build_overlay_writes_never_writes_direction():
    ov = TradeOverlay(direction="short", entry_price=100.0)
    w = comp.build_overlay_writes(ov, ["direction", "entry_price"])
    assert "direction" not in w
    assert all(not str(k).startswith("nt_dir") for k in w)
    assert w == {"nt_entry": 100.0}
