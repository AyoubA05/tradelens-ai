"""
"Ask AI About This Trade" (Session D1).

Service-level: the system prompt must forbid live signals and the trade context
must carry the key fields. UI-level: disabled / no-trade states show info, not a
crash.
"""

from pathlib import Path

import src.tradelens.services.ai_client as ai_client
from src.tradelens.services.partner import (
    build_partner_system,
    build_trade_context,
    partner_reply,
)
from src.tradelens.services.partner import _DEMO_PARTNER_REPLY

ROOT = str(Path(__file__).resolve().parents[1])


def test_ask_ai_post_trade_system_prompt():
    system = build_partner_system().lower()
    assert "signal" in system
    assert "predict" in system or "prediction" in system
    assert "post-trade" in system


def test_ask_ai_trade_context_included():
    trade = {
        "trade_date": "2026-06-24",
        "asset": "NQ",
        "direction": "Long",
        "result": "Win",
        "pnl": 250.0,
    }
    ctx = build_trade_context(trade)
    for field in ("2026-06-24", "NQ", "Long", "Win"):
        assert field in ctx


def test_ask_ai_demo_mode_returns_canned_reply(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "demo_mode", True)
    reply, _usage = partner_reply([{"role": "user", "content": "What did I do well?"}])
    assert reply == _DEMO_PARTNER_REPLY


# ── UI states (AppTest, no network) ───────────────────────────────


def _all_text(at) -> str:
    parts = []
    for attr in ("info", "warning", "markdown", "caption", "subheader"):
        try:
            parts.extend(str(getattr(e, "value", "")) for e in getattr(at, attr))
        except Exception:
            pass
    return " ".join(parts)


def _run(setup_line: str, call: str):
    from streamlit.testing.v1 import AppTest

    script = (
        f"import sys\n"
        f'sys.path.insert(0, r"{ROOT}")\n'
        "import src.tradelens.ui.components.ai_trade_chat as chat_mod\n"
        f"{setup_line}\n"
        f"chat_mod.render_ask_ai({call})\n"
    )
    return AppTest.from_string(script).run()


def test_ask_ai_disabled_state():
    at = _run("chat_mod.is_ai_enabled = lambda: False", "None")
    assert not at.exception
    text = _all_text(at)
    assert "disabled" in text.lower() or "Settings" in text


def test_ask_ai_no_trade_selected():
    at = _run("chat_mod.is_ai_enabled = lambda: True", "None")
    assert not at.exception
    assert "Select a trade" in _all_text(at)
