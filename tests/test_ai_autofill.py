"""
AI Autofill mapping (Session F, Phase 1).

Pure, Streamlit-free mapping from the screenshot_v2 vision output to New Trade
form values. AI proposes descriptive fields only (asset, timeframe, HTF/LTF bias,
confluence flags); trade_quality / mistakes / notes stay read-only observations.
No prices, no direction — this is post-trade reflection, never a signal.
"""

from src.tradelens.services.ai_autofill import (
    AutofillResult,
    confluences_from_analysis,
    map_analysis_to_form,
    normalize_bias,
    normalize_timeframe,
)

# ---------------------------------------------------------------------------
# normalize_bias
# ---------------------------------------------------------------------------


def test_normalize_bias_bullish():
    assert normalize_bias("bullish") == "Bullish"


def test_normalize_bias_bearish():
    assert normalize_bias("bearish") == "Bearish"


def test_normalize_bias_neutral_maps_to_consolidation():
    assert normalize_bias("neutral") == "Consolidation"


def test_normalize_bias_consolidation_and_ranging():
    assert normalize_bias("consolidation") == "Consolidation"
    assert normalize_bias("ranging") == "Consolidation"


def test_normalize_bias_is_case_insensitive():
    assert normalize_bias("BULLISH") == "Bullish"


def test_normalize_bias_none():
    assert normalize_bias(None) is None


def test_normalize_bias_unknown_returns_none():
    assert normalize_bias("moon") is None
    assert normalize_bias("") is None


# ---------------------------------------------------------------------------
# normalize_timeframe
# ---------------------------------------------------------------------------


def test_normalize_timeframe_passthrough_known():
    assert normalize_timeframe("15m") == "15m"
    assert normalize_timeframe("1m") == "1m"
    assert normalize_timeframe("5m") == "5m"


def test_normalize_timeframe_hour_variants():
    assert normalize_timeframe("1H") == "1H"
    assert normalize_timeframe("1h") == "1H"
    assert normalize_timeframe("4h") == "4H"


def test_normalize_timeframe_minutes_to_hour():
    assert normalize_timeframe("60m") == "1H"
    assert normalize_timeframe("240m") == "4H"


def test_normalize_timeframe_daily():
    assert normalize_timeframe("Daily") == "D"
    assert normalize_timeframe("1D") == "D"
    assert normalize_timeframe("d") == "D"


def test_normalize_timeframe_unsupported_returns_none():
    assert normalize_timeframe("30m") is None
    assert normalize_timeframe("weekly") is None


def test_normalize_timeframe_none():
    assert normalize_timeframe(None) is None


# ---------------------------------------------------------------------------
# confluences_from_analysis
# ---------------------------------------------------------------------------


def test_confluences_maps_all_flags_in_canonical_order():
    analysis = {
        "liquidity_sweep": True,
        "fvg_used": True,
        "order_block_used": True,
        "bos": True,
        "choch": True,
    }
    assert confluences_from_analysis(analysis) == [
        "Liquidity Sweep",
        "FVG",
        "OB Retest",
        "BOS",
        "MSS/CHOCH",
    ]


def test_confluences_excludes_falsy_and_missing():
    analysis = {"bos": True, "fvg_used": False, "liquidity_sweep": None}
    assert confluences_from_analysis(analysis) == ["BOS"]


def test_confluences_empty_when_no_flags():
    assert confluences_from_analysis({}) == []


# ---------------------------------------------------------------------------
# map_analysis_to_form
# ---------------------------------------------------------------------------


def _full_analysis() -> dict:
    return {
        "bias": "bearish",
        "htf_bias": "bullish",
        "detected_timeframe": "15m",
        "detected_asset": "NQ",
        "bos": True,
        "fvg_used": True,
        "trade_quality": 7,
        "possible_mistakes": ["Late entry"],
        "missed_opportunities": ["Earlier FVG"],
        "notes_to_user": "Waited for confirmation.",
        "structure": "Bearish BOS after sweep.",
        "matched_strategy": "ICT Silver Bullet",
        "matched_strategy_reason": "London FVG continuation.",
        "key_zones": [{"type": "fvg", "description": "15m FVG"}],
        "bias_confidence": 0.8,
    }


def test_map_returns_autofill_result():
    assert isinstance(map_analysis_to_form(_full_analysis()), AutofillResult)


def test_map_splits_bias_into_htf_and_ltf():
    # vision "bias" -> LTF bias; vision "htf_bias" -> HTF bias
    result = map_analysis_to_form(_full_analysis())
    assert result.prefill["ltf_bias"] == "Bearish"
    assert result.prefill["htf_bias"] == "Bullish"


def test_map_populates_timeframe_and_asset():
    result = map_analysis_to_form(_full_analysis())
    assert result.prefill["timeframe"] == "15m"
    assert result.prefill["asset"] == "NQ"


def test_map_populates_confluences_from_flags():
    result = map_analysis_to_form(_full_analysis())
    assert result.prefill["confluences"] == ["FVG", "BOS"]


def test_map_ai_fields_tracks_only_present_fields():
    analysis = {"bias": "bullish"}  # only LTF bias is usable
    result = map_analysis_to_form(analysis)
    assert result.ai_fields == ["ltf_bias"]
    assert "timeframe" not in result.prefill
    assert "asset" not in result.prefill


def test_map_omits_none_and_unmappable_fields():
    analysis = {"bias": None, "detected_timeframe": "30m", "detected_asset": None}
    result = map_analysis_to_form(analysis)
    assert result.prefill == {}
    assert result.ai_fields == []


def test_map_does_not_propose_direction_or_price():
    # Hard project-identity guard: no signal-shaped fields ever leak into prefill.
    result = map_analysis_to_form(_full_analysis())
    for forbidden in (
        "direction",
        "entry_price",
        "stop_price",
        "tp_price",
        "exit_price",
        "pnl",
        "result",
    ):
        assert forbidden not in result.prefill


def test_map_extracts_read_only_observations():
    result = map_analysis_to_form(_full_analysis())
    assert result.observations["trade_quality"] == 7
    assert result.observations["possible_mistakes"] == ["Late entry"]
    assert result.observations["notes_to_user"] == "Waited for confirmation."
    assert result.observations["matched_strategy"] == "ICT Silver Bullet"


def test_map_observations_never_appear_in_prefill():
    result = map_analysis_to_form(_full_analysis())
    for obs_key in ("trade_quality", "possible_mistakes", "notes_to_user"):
        assert obs_key not in result.prefill


def test_map_asset_in_list_true_when_known():
    result = map_analysis_to_form(_full_analysis(), known_assets=["NQ", "ES"])
    assert result.asset_in_list is True


def test_map_asset_in_list_false_when_unknown():
    analysis = {"detected_asset": "TSLA"}
    result = map_analysis_to_form(analysis, known_assets=["NQ", "ES"])
    assert result.asset_in_list is False
    assert result.prefill["asset"] == "TSLA"


def test_map_asset_normalizes_slashes_for_matching():
    analysis = {"detected_asset": "gbp/usd"}
    result = map_analysis_to_form(analysis, known_assets=["GBPUSD"])
    assert result.prefill["asset"] == "GBPUSD"
    assert result.asset_in_list is True


def test_map_asset_in_list_none_when_no_known_assets():
    result = map_analysis_to_form(_full_analysis())
    assert result.asset_in_list is None


def test_map_none_analysis_returns_empty_result():
    result = map_analysis_to_form(None)
    assert result.prefill == {}
    assert result.ai_fields == []
    assert result.observations == {}
    assert result.asset_in_list is None


def test_map_non_dict_analysis_returns_empty_result():
    result = map_analysis_to_form("not a dict")
    assert result.prefill == {}
    assert result.ai_fields == []


# ---------------------------------------------------------------------------
# Hardening (Session F, Phase 1 — code-review follow-up)
# ---------------------------------------------------------------------------


def test_confluence_string_false_is_not_truthy():
    # A flag returned as the string "false" must NOT become a confluence.
    assert confluences_from_analysis({"bos": "false"}) == []


def test_confluence_arbitrary_string_is_not_truthy():
    assert confluences_from_analysis({"fvg_used": "maybe"}) == []


def test_confluence_true_like_values_are_accepted():
    # Real booleans and the canonical true-like encodings still map.
    assert confluences_from_analysis({"bos": True}) == ["BOS"]
    assert confluences_from_analysis({"bos": 1}) == ["BOS"]
    assert confluences_from_analysis({"bos": "true"}) == ["BOS"]


def test_confluence_false_like_values_are_rejected():
    assert confluences_from_analysis({"bos": 0}) == []
    assert confluences_from_analysis({"bos": "0"}) == []
    assert confluences_from_analysis({"bos": "no"}) == []


def test_map_non_string_asset_fails_safe():
    # A malformed (non-string) detected_asset omits the prefill, never crashes.
    result = map_analysis_to_form({"detected_asset": 123})
    assert "asset" not in result.prefill
    assert result.asset_in_list is None


def test_map_non_string_asset_fails_safe_with_known_assets():
    result = map_analysis_to_form({"detected_asset": ["NQ"]}, known_assets=["NQ"])
    assert "asset" not in result.prefill
    assert result.asset_in_list is None


def test_map_list_observations_default_to_empty_list():
    obs = map_analysis_to_form({}).observations
    assert obs["possible_mistakes"] == []
    assert obs["missed_opportunities"] == []
    assert obs["key_zones"] == []


def test_map_confluences_only_analysis():
    result = map_analysis_to_form({"bos": True, "fvg_used": True})
    assert result.prefill == {"confluences": ["FVG", "BOS"]}
    assert result.ai_fields == ["confluences"]


def test_map_asset_in_list_false_with_empty_known_assets():
    result = map_analysis_to_form({"detected_asset": "NQ"}, known_assets=[])
    assert result.prefill["asset"] == "NQ"
    assert result.asset_in_list is False


def test_map_bias_strips_whitespace():
    result = map_analysis_to_form({"bias": "  bearish  "})
    assert result.prefill["ltf_bias"] == "Bearish"
