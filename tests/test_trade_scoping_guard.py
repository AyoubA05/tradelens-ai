"""Every live journal read is scoped to one account.

``get_trades`` requires ``user_id`` — there is no unscoped default. It used to
default to an ``_UNSCOPED`` sentinel that applied no owner filter at all,
supposedly load-bearing for the metrics recompute script; that script instead
had a defect (it accepted an owner and then read every user's trades) and is
now scoped like everything else, so nothing needs the sentinel and it was
deleted.

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

from src.tradelens.services import trade_service, weekly

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


def test_user_id_has_no_default():
    """No unscoped escape hatch remains — every caller must name a real owner."""
    signature = inspect.signature(trade_service.get_trades)
    assert signature.parameters["user_id"].default is inspect.Parameter.empty


# ---------------------------------------------------------------------------
# Weekly review write/generate path (Tasks 2+3 review, closed alongside
# Task 4). ``save_weekly_review`` used to default ``user_id`` to None, which
# filtered and stamped rows with ``user_id IS NULL`` — a write-side hole into
# the legacy shared tenant. ``generate_weekly_review`` was only transitively
# scoped, via ``get_trades``. Both now require a real owner; these guard
# tests fail loudly if a future edit reintroduces a default.
# ---------------------------------------------------------------------------


def test_save_weekly_review_user_id_has_no_default():
    signature = inspect.signature(weekly.save_weekly_review)
    assert signature.parameters["user_id"].default is inspect.Parameter.empty


def test_generate_weekly_review_user_id_has_no_default():
    signature = inspect.signature(weekly.generate_weekly_review)
    assert signature.parameters["user_id"].default is inspect.Parameter.empty


def test_save_weekly_review_refuses_none_owner():
    with pytest.raises(ValueError):
        weekly.save_weekly_review({"week_start": "2026-06-15"}, user_id=None)  # type: ignore[arg-type]


def test_generate_weekly_review_refuses_none_owner():
    with pytest.raises(ValueError):
        weekly.generate_weekly_review("2026-06-17", user_id=None)  # type: ignore[arg-type]
