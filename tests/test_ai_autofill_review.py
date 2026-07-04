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


# ---------------------------------------------------------------------------
# build_overlay_writes — PnL is opt-in and wired to the real nt_pnl form key;
# risk/reward ratio is cross-check only and never written.
# ---------------------------------------------------------------------------


def test_build_overlay_writes_maps_pnl_when_selected():
    ov = TradeOverlay(entry_price=100.0, pnl=172.25)
    w = comp.build_overlay_writes(ov, ["entry_price", "pnl"])
    assert w == {"nt_entry": 100.0, "nt_pnl": 172.25}


def test_build_overlay_writes_pnl_only_written_when_selected():
    ov = TradeOverlay(pnl=172.25)
    assert comp.build_overlay_writes(ov, ["entry_price"]) == {}


def test_build_overlay_writes_pnl_none_skipped():
    assert comp.build_overlay_writes(TradeOverlay(pnl=None), ["pnl"]) == {}


def test_build_overlay_writes_never_writes_rr():
    ov = TradeOverlay(entry_price=100.0, risk_reward_ratio="2.01:1", pnl=50.0)
    w = comp.build_overlay_writes(ov, ["entry_price", "risk_reward_ratio", "pnl"])
    assert w == {"nt_entry": 100.0, "nt_pnl": 50.0}
    assert "nt_r" not in w


# ---------------------------------------------------------------------------
# should_autocheck — confidence-gated defaults for the detected-markup boxes.
# Entry/stop pre-check at >= 0.70 confidence; everything else stays opt-in.
# ---------------------------------------------------------------------------


def test_autocheck_entry_and_stop_at_threshold():
    assert comp.should_autocheck("entry_price", 0.70) is True
    assert comp.should_autocheck("stop_price", 0.95) is True


def test_autocheck_below_threshold_stays_unchecked():
    assert comp.should_autocheck("entry_price", 0.69) is False
    assert comp.should_autocheck("stop_price", 0.0) is False


def test_autocheck_never_for_tp_exit_or_pnl():
    assert comp.should_autocheck("tp_price", 0.99) is False
    assert comp.should_autocheck("exit_price", 0.99) is False
    assert comp.should_autocheck("pnl", 0.99) is False


def test_autocheck_missing_or_junk_confidence_stays_unchecked():
    assert comp.should_autocheck("entry_price", None) is False
    assert comp.should_autocheck("entry_price", "high") is False


# ---------------------------------------------------------------------------
# build_review_outcome — accepted / accepted_with_edits / rejected record that
# persists with the analysis (inside raw_response_json; no schema change).
# ---------------------------------------------------------------------------


def test_review_outcome_accepted_as_is():
    rec = comp.build_review_outcome("accepted", ["entry_price", "timeframe"], [])
    assert rec == {
        "outcome": "accepted",
        "applied_fields": ["entry_price", "timeframe"],
        "edited_fields": [],
    }


def test_review_outcome_accepted_with_edits():
    rec = comp.build_review_outcome("accepted", ["entry_price"], {"entry_price"})
    assert rec["outcome"] == "accepted_with_edits"
    assert rec["edited_fields"] == ["entry_price"]


def test_review_outcome_rejected():
    rec = comp.build_review_outcome("rejected", [], [])
    assert rec == {"outcome": "rejected", "applied_fields": [], "edited_fields": []}


def test_review_outcome_none_when_trader_never_decided():
    assert comp.build_review_outcome(None, ["entry_price"], []) is None
    assert comp.build_review_outcome("", [], []) is None


# ---------------------------------------------------------------------------
# observation_summary — compact-first AI observations (full text preserved in
# the expander; the summary never destroys information).
# ---------------------------------------------------------------------------


def test_observation_summary_uses_notes_first():
    obs = {"notes_to_user": "Solid entry off the FVG.", "trade_quality": 7}
    assert comp.observation_summary(obs) == "Solid entry off the FVG."


def test_observation_summary_truncates_long_notes_on_word_boundary():
    obs = {"notes_to_user": "word " * 80}
    s = comp.observation_summary(obs, max_len=60)
    assert len(s) <= 61  # 60 + ellipsis char
    assert s.endswith("…")


def test_observation_summary_falls_back_to_quality():
    assert comp.observation_summary({"trade_quality": 6}) == "AI quality estimate: 6/10"


def test_observation_summary_none_when_nothing_to_say():
    assert comp.observation_summary({}) is None
    assert comp.observation_summary({"notes_to_user": "  "}) is None


# ---------------------------------------------------------------------------
# Item 2 — autofill auto-triggers on a new screenshot source (no button press).
# ---------------------------------------------------------------------------


def test_source_signature_distinguishes_sources():
    from types import SimpleNamespace

    f = SimpleNamespace(name="chart.png", size=123, file_id="abc")
    assert comp._source_signature(f, None) == ("file", "abc")
    assert comp._source_signature(None, "https://x.com/a.png") == (
        "url",
        "https://x.com/a.png",
    )
    assert comp._source_signature(None, None) is None
    # file wins over URL when both are present (matches _analyze precedence)
    assert comp._source_signature(f, "https://x.com/a.png")[0] == "file"


def test_source_signature_falls_back_to_name_size():
    from types import SimpleNamespace

    f = SimpleNamespace(name="chart.png", size=123)
    assert comp._source_signature(f, None) == ("file", ("chart.png", 123))


def _autotrigger_apptest(run_count: int):
    """AppTest: render with a file present, _analyze patched to count calls."""
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    root = Path(__file__).resolve().parents[1]
    script = (
        "import sys\n"
        f'sys.path.insert(0, r"{root}")\n'
        "from types import SimpleNamespace\n"
        "import streamlit as st\n"
        "import src.tradelens.ui.components.ai_autofill_review as comp\n"
        "comp._ai_available = lambda: True\n"
        "st.session_state.setdefault('_calls', 0)\n"
        "def _fake_analyze(*a, **k):\n"
        "    st.session_state['_calls'] += 1\n"
        "comp._analyze = _fake_analyze\n"
        "f = SimpleNamespace(name='chart.png', size=9, file_id='f1')\n"
        "comp.render_autofill_review(screenshot_file=f, screenshot_url=None, "
        "strategy_profile=None, known_assets=['NQ'])\n"
    )
    at = AppTest.from_string(script)
    at.run()
    for _ in range(run_count - 1):
        at.run()
    return at


def test_analysis_autoruns_once_without_button_press():
    at = _autotrigger_apptest(run_count=1)
    assert not at.exception
    assert at.session_state["_calls"] == 1  # ran with zero button clicks


def test_same_source_does_not_retrigger_on_rerun():
    at = _autotrigger_apptest(run_count=3)
    assert not at.exception
    assert at.session_state["_calls"] == 1  # signature blocks repeat runs
