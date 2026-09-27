"""The gate-2 budget gate stops requests before they are made (no spend)."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

_spec = importlib.util.spec_from_file_location(
    "gate2", Path(__file__).resolve().parents[1] / "scripts" / "gate_anthropic_smoke.py"
)
gate2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate2)

RATES = {"input": 5.0, "output": 25.0}


def _fake_ai_client():
    def estimate(model, tin, tout, cr=0, cw=0):
        return (tin * RATES["input"] + tout * RATES["output"]) / 1_000_000

    return SimpleNamespace(_estimate_cost=estimate)


def _create(input_tokens, output_tokens, made):
    def real_create(**kwargs):
        made.append(kwargs)
        return SimpleNamespace(
            usage=SimpleNamespace(
                input_tokens=input_tokens, output_tokens=output_tokens
            ),
            stop_reason="end_turn",
        )

    return real_create


def test_the_thirteenth_request_is_never_made():
    gate, made = gate2.Gate(_fake_ai_client(), RATES), []
    create = _create(100, 100, made)
    for _ in range(gate2.MAX_CALLS):
        gate.create(
            create, "m", messages=[{"role": "user", "content": "x"}], max_tokens=64
        )
    with pytest.raises(gate2.BudgetStop):
        gate.create(create, "m", messages=[], max_tokens=64)
    assert len(made) == gate2.MAX_CALLS == 12


def test_spend_at_the_stop_line_stops_further_requests():
    gate, made = gate2.Gate(_fake_ai_client(), RATES), []
    gate.spent = gate2.STOP_AT_USD
    with pytest.raises(gate2.BudgetStop, match="stop line"):
        gate.create(_create(1, 1, made), "m", messages=[], max_tokens=1)
    assert made == []


def test_a_request_whose_worst_case_breaches_the_cap_is_refused():
    gate, made = gate2.Gate(_fake_ai_client(), RATES), []
    gate.spent = 3.9  # below the stop line
    # 128k max_tokens at $25/M is $3.20 worst case: 3.9 + 3.2 > 5.00
    with pytest.raises(gate2.BudgetStop, match="cap"):
        gate.create(_create(1, 1, made), "m", messages=[], max_tokens=128_000)
    assert made == []


def test_provider_reported_usage_is_what_gets_counted():
    gate, made = gate2.Gate(_fake_ai_client(), RATES), []
    gate.create(_create(10_000, 2_000, made), "m", messages=[], max_tokens=4096)
    assert gate.spent == pytest.approx((10_000 * 5 + 2_000 * 25) / 1_000_000)
    assert gate.log[0]["input_tokens"] == 10_000 and gate.calls == 1
