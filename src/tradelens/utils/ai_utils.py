"""
AI availability helper (Session B, Section 5).

One place to ask "is the Anthropic key configured?" so the UI can disable AI
actions and show a clean message instead of leaking a raw key error. Reads
st.secrets when available, falling back to the environment.
"""

from __future__ import annotations

import os


def is_ai_enabled() -> bool:
    """True when an Anthropic API key is configured (secrets or environment)."""
    try:
        import streamlit as st

        key = st.secrets.get("ANTHROPIC_API_KEY")
        if key:
            return bool(key)
    except Exception:  # noqa: BLE001 — no secrets file in tests/CLI is normal
        pass
    return bool(os.getenv("ANTHROPIC_API_KEY"))
