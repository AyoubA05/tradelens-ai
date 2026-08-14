"""An optional convenience must not be able to take the application down.

``bootstrap_if_local()`` creates a local SQLite file for development. Against a
deployed database it inspects the engine, sees the target is not a local SQLite
file, and returns without touching anything — it is a no-op in production by
design.

It was nonetheless imported at the top of ``app.py`` with a bare ``import``, so
any failure anywhere in its module chain aborted the script before a single line
of page body ran. That is what happened on Streamlit Cloud: every request on
every page returned a redacted ``ImportError`` while the application itself was
healthy, and the blast radius of a development convenience became the whole
product.

These tests pin the shape of the fix rather than the specific failure, because
the specific failure was environment-dependent and never reproduced locally —
which is precisely why the guard has to be unconditional.
"""

from __future__ import annotations

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "src" / "tradelens" / "ui" / "app.py"


def _tree() -> ast.Module:
    return ast.parse(APP.read_text(encoding="utf-8"))


def _module_level_imports(tree: ast.Module) -> list[ast.stmt]:
    """Imports executed unconditionally at module scope, outside any handler."""
    return [
        node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
    ]


def test_the_bootstrap_import_is_guarded():
    """It must live inside a try, not at bare module scope."""
    bare = [
        node
        for node in _module_level_imports(_tree())
        if isinstance(node, ast.ImportFrom)
        and node.module == "src.tradelens.db.init_db"
    ]
    assert bare == [], "bootstrap_if_local is imported without a guard"


def test_the_guard_catches_every_failure_not_just_ImportError():
    """The chain reaches a database engine; it can fail in more ways than one."""
    handlers = []
    for node in ast.walk(_tree()):
        if not isinstance(node, ast.Try):
            continue
        imports_bootstrap = any(
            isinstance(inner, ast.ImportFrom)
            and inner.module == "src.tradelens.db.init_db"
            for inner in ast.walk(node)
        )
        if imports_bootstrap:
            handlers = [
                h.type.id if isinstance(h.type, ast.Name) else None
                for h in node.handlers
            ]
    assert handlers, "no try/except wraps the bootstrap import"
    assert "Exception" in handlers, f"guard does not catch Exception: {handlers}"


def test_the_call_site_tolerates_a_missing_bootstrap():
    """Guarding the import is pointless if calling it then raises NameError."""
    source = APP.read_text(encoding="utf-8")
    assert "if bootstrap_if_local is not None:" in source


def test_the_failure_reason_is_logged_and_never_rendered():
    """Streamlit redacts errors in the browser on purpose; keep it that way."""
    source = APP.read_text(encoding="utf-8")
    assert "_BOOTSTRAP_IMPORT_ERROR" in source
    assert "_boot_log.warning(" in source
    # The reason must not reach the page.
    for rendered in (
        "st.error(_BOOTSTRAP_IMPORT_ERROR",
        "_st_boot.error(_BOOTSTRAP_IMPORT_ERROR",
        "st.write(_BOOTSTRAP_IMPORT_ERROR",
        "st.exception(",
    ):
        assert rendered not in source, rendered


def test_only_an_import_failure_contributes_its_message():
    """A driver error's message can carry the DSN; an ImportError's cannot.

    So the ImportError handler may format `exc`, and the general handler may
    record the class name only.
    """
    tree = _tree()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        if not any(
            isinstance(inner, ast.ImportFrom)
            and inner.module == "src.tradelens.db.init_db"
            for inner in ast.walk(node)
        ):
            continue
        for handler in node.handlers:
            caught = handler.type.id if isinstance(handler.type, ast.Name) else None
            body = ast.unparse(handler)
            if caught == "Exception":
                assert "type(exc).__name__" in body
                # No bare interpolation of the exception itself.
                assert "{exc}" not in body


def test_the_session_import_stays_unguarded():
    """Deliberate asymmetry: guard what is optional, surface what is not.

    ``DatabaseUnavailableError`` comes from the module every service depends on.
    If that cannot be imported the application genuinely cannot work, and
    masking it would move the crash somewhere less honest.
    """
    unguarded = [
        node
        for node in _module_level_imports(_tree())
        if isinstance(node, ast.ImportFrom)
        and node.module == "src.tradelens.db.session"
    ]
    assert len(unguarded) == 1
