"""
AI availability helper (Session B, Section 5).

One place to ask "is the Anthropic key configured?" so the UI can disable AI
actions and show a clean message instead of leaking a raw key error. Reads
st.secrets when available, falling back to the environment.
"""

from __future__ import annotations

import os


def ai_available() -> bool:
    """True when AI output is possible: a key is configured OR demo mode is on
    (demo serves cached fixtures with zero spend). One shared gate so pages and
    components can't drift apart on whether demo users see AI sections.
    """
    try:
        from src.tradelens.services.demo import is_demo

        if is_demo():
            return True
    except Exception:  # noqa: BLE001 — a demo-check failure must not kill the gate
        pass
    return is_ai_enabled()


def is_ai_enabled() -> bool:
    """True when an Anthropic API key is configured (secrets or environment).

    Delegates to the AI client's resolver so the UI availability gate and the
    actual API call can never disagree — the root of Bug 5, where the gate read
    ``st.secrets`` but the client read ``settings``/env. Falls back to a bare env
    check only if the client can't be imported.
    """
    try:
        from src.tradelens.services.ai_client import has_api_key

        return has_api_key()
    except Exception:  # noqa: BLE001 — keep the gate working even if imports fail
        return bool(os.getenv("ANTHROPIC_API_KEY"))
