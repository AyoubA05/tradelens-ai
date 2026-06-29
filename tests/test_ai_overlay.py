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


def test_parse_never_exposes_pnl_or_result():
    # P&L / result stay manual for MVP — the overlay must not carry them.
    analysis = {"trade_overlay": {"pnl": 250.0, "result": "Win", "source": "none"}}
    ov = parse_trade_overlay(analysis)
    assert not hasattr(ov, "pnl")
    assert not hasattr(ov, "result")


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
