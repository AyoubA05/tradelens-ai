"""Every live journal read is scoped to one account.

``get_trades``'s user filter defaults to *unscoped* — omit the argument and it
returns every trade in the table, across all accounts. That default is load
bearing for one legitimate caller (the metrics recompute script, which really
does operate over everything), so it cannot simply be made required without
inventing a way to say "all users" that reads as deliberately as the current
omission reads as accidental.

What can be guaranteed cheaply is the property that actually matters: no page
or service the application routes to may read the journal unscoped. That is
asserted here structurally, because it is the kind of thing a future page adds
by copying a line from an archived one.

Archived pages under ``_archive/`` are excluded. They are not routed, and
Streamlit only registers files directly under ``pages/``.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from src.tradelens.services import trade_service

ROOT = Path(__file__).resolve().parents[1]
LIVE_DIRS = [ROOT / "src" / "tradelens" / "ui", ROOT / "src" / "tradelens" / "services"]


def live_sources():
    for base in LIVE_DIRS:
        for path in sorted(base.rglob("*.py")):
            if "_archive" in path.parts or "__pycache__" in path.parts:
                continue
            yield path


def test_every_live_caller_scopes_the_journal_to_a_user():
    """The isolation property, checked at every call site rather than one."""
    offenders = []
    for path in live_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.attr
                if isinstance(func, ast.Attribute)
                else func.id if isinstance(func, ast.Name) else ""
            )
            if name != "get_trades":
                continue
            # The definition itself, and the weekly service's own signature.
            if not any(kw.arg == "user_id" for kw in node.keywords):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")

    assert offenders == [], f"unscoped journal reads: {offenders}"


def test_get_trades_refuses_positional_arguments():
    """The footgun: `get_trades(uid)` meant `start_date=uid`, silently."""
    with pytest.raises(TypeError):
        trade_service.get_trades(1)  # type: ignore[misc]


def test_every_parameter_is_keyword_only():
    signature = inspect.signature(trade_service.get_trades)
    positional = [
        name
        for name, parameter in signature.parameters.items()
        if parameter.kind
        in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD)
    ]
    assert positional == []


def test_the_unscoped_default_is_still_reachable_on_purpose():
    """Kept, because the metrics recompute legitimately spans every account.

    Documented here so removing it later is a decision rather than a surprise.
    """
    signature = inspect.signature(trade_service.get_trades)
    assert signature.parameters["user_id"].default is trade_service._UNSCOPED
