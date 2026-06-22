"""
Gates for the runtime/dev requirements split (Phase 7, week6-d7).

The deployed app installs only requirements.txt, so no test/lint tool may leak
into it; requirements-dev.txt must pull in the runtime set and add the dev tools.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = (ROOT / "requirements.txt").read_text(encoding="utf-8")
DEV = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")

_DEV_TOOLS = ["pytest", "pytest-cov", "black", "ruff", "faker"]
_RUNTIME_CORE = [
    "streamlit",
    "pandas",
    "anthropic",
    "sqlalchemy",
    "alembic",
    "plotly",
    "pydantic-settings",
]


def _dep_names(text: str) -> set:
    names = set()
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or ln.startswith("-r "):
            continue
        names.add(ln.split("==")[0].split(">=")[0].strip())
    return names


def test_runtime_has_core_deps():
    names = _dep_names(RUNTIME)
    for dep in _RUNTIME_CORE:
        assert dep in names, f"runtime requirements.txt missing {dep}"


def test_runtime_has_no_dev_tools():
    names = _dep_names(RUNTIME)
    for tool in _DEV_TOOLS:
        assert tool not in names, f"dev tool {tool} must not be in runtime requirements.txt"


def test_dev_references_runtime():
    assert "-r requirements.txt" in DEV


def test_dev_has_all_dev_tools():
    names = _dep_names(DEV)
    for tool in _DEV_TOOLS:
        assert tool in names, f"requirements-dev.txt missing {tool}"
