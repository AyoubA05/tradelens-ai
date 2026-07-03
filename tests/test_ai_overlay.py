"""
Trade-overlay parsing (Session F, Phase 3).

The `trade_overlay` section of the screenshot_v3 analysis is a SEPARATE path from
the descriptive autofill: it carries the visible trade-box / chart-markup geometry
(direction + prices) with per-field confidence. These are approximate, never
auto-applied, and never flow through ai_autofill.map_analysis_to_form.
"""

from src.tradelens.services.ai_overlay import (
    OVERLAY_PRICE_FIELDS,
    TradeOverlay,
    descriptive_section,
    parse_trade_overlay,
)


def _full_overlay() -> dict:
    return {
        "trade_overlay": {
            "direction": "short",
            "entry_price": 19850.25,
            "stop_price": 19880.0,
            "tp_price": 19790.0,
            "exit_price": 19805.0,
            "confidence": {
                "direction": 0.8,
                "entry_price": 0.7,
                "stop_price": 0.65,
                "tp_price": 0.6,
                "exit_price": 0.5,
            },
            "source": "visible_trade_box",
        }
    }


# ---------------------------------------------------------------------------
# parse_trade_overlay
# ---------------------------------------------------------------------------


def test_parse_full_overlay_keeps_prices_and_source():
    ov = parse_trade_overlay(_full_overlay())
    assert ov.direction == "short"
    assert ov.entry_price == 19850.25
    assert ov.stop_price == 19880.0
    assert ov.tp_price == 19790.0
    assert ov.exit_price == 19805.0
    assert ov.source == "visible_trade_box"
    assert ov.has_prices() is True


def test_parse_records_clamped_confidence_per_field():
    ov = parse_trade_overlay(_full_overlay())
    assert ov.confidence["entry_price"] == 0.7
    assert ov.confidence["direction"] == 0.8


def test_parse_clamps_out_of_range_confidence():
    analysis = {
        "trade_overlay": {
            "entry_price": 100.0,
            "confidence": {"entry_price": 1.7},
            "source": "visible_chart_markup",
        }
    }
    ov = parse_trade_overlay(analysis)
    assert ov.confidence["entry_price"] == 1.0


def test_parse_no_overlay_is_empty_source_none():
    ov = parse_trade_overlay({"descriptive": {"bias": "bullish"}})
    assert ov.source == "none"
    assert ov.has_prices() is False
    assert ov.direction is None


def test_parse_non_dict_analysis_is_empty():
    ov = parse_trade_overlay("not a dict")
    assert isinstance(ov, TradeOverlay)
    assert ov.has_prices() is False
    assert ov.source == "none"


def test_parse_invalid_direction_and_source_drop_to_safe():
    analysis = {"trade_overlay": {"direction": "sideways", "source": "made_up"}}
    ov = parse_trade_overlay(analysis)
    assert ov.direction is None
    assert ov.source == "none"


def test_parse_non_numeric_price_becomes_none():
    analysis = {"trade_overlay": {"entry_price": "n/a", "stop_price": True}}
    ov = parse_trade_overlay(analysis)
    assert ov.entry_price is None
    assert ov.stop_price is None  # bool is not a usable price


def test_parse_min_confidence_drops_low_confidence_prices():
    analysis = {
        "trade_overlay": {
            "entry_price": 100.0,
            "stop_price": 95.0,
            "confidence": {"entry_price": 0.8, "stop_price": 0.3},
            "source": "visible_trade_box",
        }
    }
    ov = parse_trade_overlay(analysis, min_confidence=0.5)
    assert ov.entry_price == 100.0
    assert ov.stop_price is None  # 0.3 < 0.5 → dropped


def test_overlay_price_fields_constant():
    assert OVERLAY_PRICE_FIELDS == (
        "entry_price",
        "stop_price",
        "tp_price",
        "exit_price",
    )


def test_parse_extracts_pnl_but_not_result():
    # PnL is now transcribed from a visible "Closed PnL" label (approved change);
    # the trade RESULT (Win/Loss) still stays the trader's to enter — never parsed.
    analysis = {
        "trade_overlay": {"pnl": 250.0, "result": "Win", "source": "visible_trade_box"}
    }
    ov = parse_trade_overlay(analysis)
    assert ov.pnl == 250.0
    assert not hasattr(ov, "result")


# ---------------------------------------------------------------------------
# Extraction-contract additions (screenshot_v3 field extension):
# pnl, risk_reward_ratio, overall_confidence, visible_labels — all fail-safe.
# ---------------------------------------------------------------------------


def test_parse_pnl_numeric():
    assert parse_trade_overlay({"trade_overlay": {"pnl": 172.25}}).pnl == 172.25


def test_parse_pnl_negative_allowed():
    # A loss is a real, visible Closed PnL — negatives must survive.
    assert parse_trade_overlay({"trade_overlay": {"pnl": -85.75}}).pnl == -85.75


def test_parse_pnl_strips_commas_and_currency():
    assert parse_trade_overlay({"trade_overlay": {"pnl": "1,234.50"}}).pnl == 1234.5
    assert parse_trade_overlay({"trade_overlay": {"pnl": "$172.25"}}).pnl == 172.25


def test_parse_pnl_rejects_bool():
    assert parse_trade_overlay({"trade_overlay": {"pnl": True}}).pnl is None


def test_parse_pnl_none_when_missing_or_garbage():
    assert parse_trade_overlay({"trade_overlay": {"source": "none"}}).pnl is None
    assert parse_trade_overlay({"trade_overlay": {"pnl": "n/a"}}).pnl is None


def test_parse_risk_reward_ratio_normalizes_to_ratio_string():
    def rr(v):
        return parse_trade_overlay(
            {"trade_overlay": {"risk_reward_ratio": v}}
        ).risk_reward_ratio

    assert rr("2.01:1") == "2.01:1"
    assert rr("2:1") == "2:1"
    assert rr(2.01) == "2.01:1"  # bare number normalized to "<r>:1"
    assert rr("3") == "3:1"


def test_parse_risk_reward_ratio_invalid_is_none():
    def rr(v):
        return parse_trade_overlay(
            {"trade_overlay": {"risk_reward_ratio": v}}
        ).risk_reward_ratio

    assert rr("abc") is None
    assert rr("") is None
    assert rr("0:1") is None  # a zero/negative ratio is not usable


def test_parse_overall_confidence_enum():
    def oc(v):
        return parse_trade_overlay(
            {"trade_overlay": {"overall_confidence": v}}
        ).overall_confidence

    assert oc("High") == "high"
    assert oc("medium") == "medium"
    assert oc("low") == "low"
    assert oc("sky-high") is None


def test_parse_visible_labels_filters_to_clean_strings():
    ov = parse_trade_overlay(
        {"trade_overlay": {"visible_labels": ["MNQU2026", " 1m ", "", 5, None]}}
    )
    assert ov.visible_labels == ["MNQU2026", "1m"]


def test_parse_visible_labels_non_list_is_empty():
    ov = parse_trade_overlay({"trade_overlay": {"visible_labels": "MNQU2026"}})
    assert ov.visible_labels == []


def test_parse_new_fields_default_when_overlay_missing():
    ov = parse_trade_overlay({"descriptive": {"bias": "bullish"}})
    assert ov.pnl is None
    assert ov.risk_reward_ratio is None
    assert ov.overall_confidence is None
    assert ov.visible_labels == []


# ---------------------------------------------------------------------------
# descriptive_section — bridge v3 `descriptive` → flat keys Phase 1 consumes
# ---------------------------------------------------------------------------


def test_descriptive_extracts_nested_section():
    analysis = {
        "descriptive": {"bias": "bearish", "detected_timeframe": "15m"},
        "trade_overlay": {"source": "none"},
    }
    flat = descriptive_section(analysis)
    assert flat["bias"] == "bearish"
    assert flat["detected_timeframe"] == "15m"
    assert "trade_overlay" not in flat


def test_descriptive_passthrough_for_flat_v2_dict():
    flat = descriptive_section({"bias": "bullish", "detected_timeframe": "1H"})
    assert flat == {"bias": "bullish", "detected_timeframe": "1H"}


def test_descriptive_matched_strategy_bool_becomes_reason():
    analysis = {
        "descriptive": {
            "matched_strategy": True,
            "matched_strategy_reason": "London FVG continuation.",
        }
    }
    flat = descriptive_section(analysis)
    assert flat["matched_strategy"] == "London FVG continuation."


def test_descriptive_matched_strategy_false_becomes_none():
    analysis = {
        "descriptive": {"matched_strategy": False, "matched_strategy_reason": "x"}
    }
    assert descriptive_section(analysis)["matched_strategy"] is None


def test_descriptive_normalizes_string_mistakes_to_list():
    analysis = {
        "descriptive": {"possible_mistakes": "Late entry", "missed_opportunities": ""}
    }
    flat = descriptive_section(analysis)
    assert flat["possible_mistakes"] == ["Late entry"]
    assert flat["missed_opportunities"] == []


def test_descriptive_non_dict_returns_empty():
    assert descriptive_section(None) == {}


# ---------------------------------------------------------------------------
# field_provenance — was a price read from a printed label, estimated from the
# drawn markup geometry, or simply not visible? Derived from visible_labels;
# no change to the vision JSON contract.
# ---------------------------------------------------------------------------


def test_provenance_none_value_is_not_visible():
    from src.tradelens.services.ai_overlay import field_provenance

    ov = TradeOverlay(source="visible_trade_box")
    assert field_provenance(ov, "entry_price") == "none"


def test_provenance_label_when_value_matches_a_visible_label():
    from src.tradelens.services.ai_overlay import field_provenance

    ov = TradeOverlay(
        stop_price=30188.0,
        visible_labels=["MNQU2026", "1m", "Stop: 30188.00"],
        source="visible_trade_box",
    )
    assert field_provenance(ov, "stop_price") == "label"


def test_provenance_label_matches_comma_formatted_label():
    from src.tradelens.services.ai_overlay import field_provenance

    ov = TradeOverlay(
        tp_price=30286.5,
        visible_labels=["Target: 30,286.50"],
        source="visible_trade_box",
    )
    assert field_provenance(ov, "tp_price") == "label"


def test_provenance_markup_when_no_label_matches():
    from src.tradelens.services.ai_overlay import field_provenance

    ov = TradeOverlay(
        entry_price=28069.75,
        visible_labels=["MNQM2026", "1m", "Stop: 27973.50"],
        source="visible_chart_markup",
    )
    assert field_provenance(ov, "entry_price") == "markup"


def test_provenance_markup_when_no_labels_at_all():
    from src.tradelens.services.ai_overlay import field_provenance

    ov = TradeOverlay(entry_price=2.755, source="visible_trade_box")
    assert field_provenance(ov, "entry_price") == "markup"


def test_provenance_small_price_does_not_false_match_timeframe_label():
    from src.tradelens.services.ai_overlay import field_provenance

    # "1m" must not count as a label read for a price of 1.0
    ov = TradeOverlay(
        entry_price=1.0, visible_labels=["1m"], source="visible_trade_box"
    )
    assert field_provenance(ov, "entry_price") == "markup"


def test_provenance_text_covers_all_states():
    from src.tradelens.services.ai_overlay import PROVENANCE_TEXT

    assert set(PROVENANCE_TEXT) == {"label", "markup", "none"}
