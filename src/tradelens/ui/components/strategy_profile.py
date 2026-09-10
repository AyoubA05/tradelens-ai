"""Streamlit's view of the playbook constants.

The definitions live in `services/strategy_playbook.py` so the API can read
them without importing ui/. These are the same objects, not copies.
"""

from __future__ import annotations

from src.tradelens.services.strategy_playbook import (  # noqa: F401 — re-exported
    SECTION_FIELDS,
    STARTER_TEMPLATE,
    profile_completion,
)


def demo_strategy_profile() -> dict[str, str]:
    return dict(STARTER_TEMPLATE)
