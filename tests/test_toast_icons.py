"""Toast icon contracts for every routed UI surface and imported component."""

import ast
from pathlib import Path
from typing import Optional

import pytest
from streamlit.errors import StreamlitAPIException
from streamlit.string_util import validate_icon_or_emoji

UI_ROOT = Path(__file__).resolve().parents[1] / "src" / "tradelens" / "ui"
ROUTED_ROOTS = (UI_ROOT / "app.py", *sorted((UI_ROOT / "pages").glob("*.py")))


def _ui_import_path(module: str) -> Optional[Path]:
    prefix = "src.tradelens.ui"
    if module != prefix and not module.startswith(prefix + "."):
        return None
    relative = module.removeprefix(prefix).lstrip(".").replace(".", "/")
    candidate = UI_ROOT / f"{relative}.py" if relative else UI_ROOT / "__init__.py"
    if candidate.exists() and "_archive" not in candidate.parts:
        return candidate
    package = UI_ROOT / relative / "__init__.py"
    return package if package.exists() and "_archive" not in package.parts else None


def live_ui_sources() -> tuple[Path, ...]:
    """Follow the routed pages' real UI imports, excluding archived surfaces."""
    pending = list(ROUTED_ROOTS)
    seen: set[Path] = set()
    while pending:
        path = pending.pop()
        if path in seen or "_archive" in path.parts:
            continue
        seen.add(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
                modules.extend(
                    f"{node.module}.{alias.name}"
                    for alias in node.names
                    if alias.name != "*"
                )
            elif isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            for module in modules:
                imported = _ui_import_path(module)
                if imported is not None and imported not in seen:
                    pending.append(imported)
    return tuple(sorted(seen))


def _toast_icons(path: Path) -> list[tuple[int, ast.AST]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "toast"
    ]
    return [
        (call.lineno, keyword.value)
        for call in calls
        for keyword in call.keywords
        if keyword.arg == "icon"
    ]


def test_live_toast_scan_reaches_imported_components():
    """A page-only scan misses the Journal components that own five toasts."""
    relative = {str(path.relative_to(UI_ROOT)) for path in live_ui_sources()}
    assert {
        "components/ai_review.py",
        "components/corrections_sidebar.py",
        "components/screenshot_analyzer.py",
    } <= relative


def test_every_live_toast_icon_is_an_inline_material_literal():
    found = []
    for path in live_ui_sources():
        for line, expression in _toast_icons(path):
            found.append((path, line))
            assert isinstance(expression, ast.Constant) and isinstance(
                expression.value, str
            ), f"{path}:{line}: toast icon must stay an inline literal"
            icon = expression.value
            assert icon.startswith(":material/") and icon.endswith(":"), (
                f"{path}:{line}: toast icon must use Streamlit Material syntax, "
                f"got {icon!r}"
            )
            try:
                validate_icon_or_emoji(icon)
            except StreamlitAPIException as exc:
                pytest.fail(f"{path}:{line}: icon={icon!r} is invalid — {exc}")

    assert found, "routed UI scan found no st.toast(..., icon=...) call sites"
