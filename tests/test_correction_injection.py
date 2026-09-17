"""
Correction-injection presence tests.

Every AI feature service routes through ai_client._complete, which injects the
<past_corrections> block. These tests mock the network client + the corrections
builder and assert each service's OUTBOUND prompt carries the block when
corrections exist. No network, no cost.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.tradelens.services import ai_client

_BLOCK = (
    "<past_corrections>\nbias: prefer 'bearish' over 'bullish'\n</past_corrections>"
)


def _fake_message(text: str = "{}") -> MagicMock:
    resp = MagicMock()
    block = MagicMock()
    block.type = "text"
    block.text = text
    resp.content = [block]
    resp.stop_reason = "end_turn"
    resp.model = "claude-fable-5"
    resp.usage.input_tokens = 10
    resp.usage.output_tokens = 5
    resp.usage.cache_read_input_tokens = 0
    return resp


@pytest.fixture()
def captured_client(monkeypatch):
    """Live mode + a mock client that records the outbound payload; corrections present."""
    monkeypatch.setattr(ai_client.settings, "demo_mode", False)
    monkeypatch.setattr(ai_client.settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(
        ai_client, "build_correction_few_shot", lambda **k: _BLOCK, raising=False
    )
    monkeypatch.setattr(ai_client, "encode_image", lambda *a, **k: "B64")

    client = MagicMock()
    client.messages.create.return_value = _fake_message("{}")
    monkeypatch.setattr(ai_client, "_get_client", lambda: client)
    return client


def _system_blob(client) -> str:
    system = client.messages.create.call_args[1].get("system")
    if system is None:
        return ""
    return system if isinstance(system, str) else system[0]["text"]


def _user_blob(client) -> str:
    """Everything the model receives in the user turn, as one string."""
    messages = client.messages.create.call_args[1]["messages"]
    parts = []
    for message in messages:
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            parts.extend(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )
    return "\n".join(parts)


def _assert_corrections_are_user_data(client) -> None:
    """The block reaches the model, and it does NOT hold system authority.

    Both halves matter. Asserting only its presence would pass if it were
    still in `system`; asserting only its absence from `system` would pass
    if it had been dropped entirely and correction memory silently stopped
    working. It is trader-typed text, so it travels as data.
    """
    assert "<past_corrections>" in _user_blob(client)
    assert "<past_corrections>" not in _system_blob(client)


def _fake_trades():
    return [
        SimpleNamespace(
            trade_date="2026-06-15",
            day_of_week="Monday",
            result="Win",
            pnl=200.0,
            rr_realized=2.0,
            killzone="ny_am",
            confirmation_model="BOS",
            mistake_tags="[]",
            htf_bias="bullish",
            setup_type="FVG",
            followed_rules=1,
        )
    ]


def test_vision_call_injects_corrections(captured_client, tmp_path):
    from src.tradelens.services.vision import analyze_screenshot

    img = tmp_path / "chart.jpg"
    img.write_bytes(b"x")
    try:
        analyze_screenshot(str(img), {"asset": "NQ"})
    except Exception:
        pass
    _assert_corrections_are_user_data(captured_client)


def test_journal_call_injects_corrections(captured_client):
    from src.tradelens.services.journal import generate_journal

    try:
        generate_journal({"asset": "NQ"}, {})
    except Exception:
        pass
    _assert_corrections_are_user_data(captured_client)


def test_grading_call_injects_corrections(captured_client):
    from src.tradelens.services.grading import grade_trade

    try:
        grade_trade({"asset": "NQ"}, None, {})
    except Exception:
        pass
    _assert_corrections_are_user_data(captured_client)


def test_patterns_call_injects_corrections(captured_client):
    from src.tradelens.services.patterns import generate_cards

    try:
        generate_cards({"total_trades": 3})
    except Exception:
        pass
    _assert_corrections_are_user_data(captured_client)


def test_weekly_call_injects_corrections(captured_client, monkeypatch):
    from src.tradelens.services import weekly

    from src.tradelens.services import app_settings

    monkeypatch.setattr(weekly, "get_trades", lambda **k: _fake_trades())
    # The review's as-of date comes from the owner's timezone (decision C6);
    # pin it so this test never reads whatever database DATABASE_URL names.
    monkeypatch.setattr(app_settings, "get_timezone", lambda _uid: "UTC")
    try:
        weekly.generate_weekly_review("2026-06-17", user_id=1)
    except Exception:
        pass
    _assert_corrections_are_user_data(captured_client)


def test_chat_uses_captured_corrections_without_a_second_database_read(
    captured_client, monkeypatch
):
    """A fingerprinted review must send the exact block it fingerprinted."""
    from src.tradelens.services import ai_client

    monkeypatch.setattr(
        ai_client,
        "_corrections_block",
        lambda: (_ for _ in ()).throw(AssertionError("unexpected second read")),
    )
    captured = "<past_corrections>\ncaptured marker\n</past_corrections>"
    ai_client.chat("review me", system_message="trusted", corrections_block=captured)

    assert captured in _user_blob(captured_client)
    assert captured not in _system_blob(captured_client)


def test_review_trader_context_never_reaches_actual_provider_system_field(
    captured_client,
):
    from src.tradelens.services import weekly

    markers = {
        "profile": "PROFILE_MARKER_61",
        "trade": "TRADE_MARKER_72",
        "pattern": "PATTERN_MARKER_83",
        "correction": "CORRECTION_MARKER_94",
    }
    model_input = {
        "week_start": "2026-09-07",
        "week_end": "2026-09-13",
        "stats": {"trades": 1, "financial_status": "measured"},
        "candidates": {
            "pattern_label": markers["pattern"],
            "source_observation": markers["trade"],
        },
        "strategy_profile": {"playbook": markers["profile"]},
        "source_trade_ids": [1],
    }
    correction_block = (
        "<past_corrections>" + markers["correction"] + "</past_corrections>"
    )
    with pytest.raises(weekly.WeeklyReviewError):
        weekly.generate_weekly_review(
            "2026-09-07",
            user_id=1,
            model_input=model_input,
            corrections_block=correction_block,
        )

    system = _system_blob(captured_client)
    user = _user_blob(captured_client)
    assert all(marker not in system for marker in markers.values())
    assert all(marker in user for marker in markers.values())


def test_converse_places_corrections_in_the_first_user_turn(captured_client):
    """The only call shape with an assistant turn in the history.

    `chat` and `vision` both hand `_complete` a single user message, so
    neither can show what happens when the history does not start with one.
    `converse` is the shape where "prepend to the first USER turn" is a real
    decision rather than a tautology — and the AI Partner is its only
    production caller, whose own tests stub `converse` outright.
    """
    from src.tradelens.services.ai_client import converse

    history = [
        {"role": "assistant", "content": "What would you like to review?"},
        {"role": "user", "content": "How did my NQ trades go?"},
    ]
    converse(history, system_message="PBASE")

    sent = captured_client.messages.create.call_args[1]["messages"]

    # Landed in the user turn, not as a new leading message and not in the
    # assistant's mouth — putting words there would have the model treat its
    # own prior turn as having said them.
    assert len(sent) == 2
    assert sent[0]["role"] == "assistant"
    assert "<past_corrections>" not in sent[0]["content"]
    assert "<past_corrections>" in sent[1]["content"]
    assert "How did my NQ trades go?" in sent[1]["content"]
    assert "<past_corrections>" not in _system_blob(captured_client)


def test_converse_does_not_mutate_the_caller_s_history(captured_client):
    """The Partner drawer keeps using its list after the call returns.

    Mutating it in place would append the correction block into the stored
    conversation, so every later turn would carry another copy.
    """
    from src.tradelens.services.ai_client import converse

    history = [{"role": "user", "content": "How did my NQ trades go?"}]
    converse(history, system_message="PBASE")

    assert history == [{"role": "user", "content": "How did my NQ trades go?"}]
