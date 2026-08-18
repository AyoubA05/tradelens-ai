"""
Gates for the runtime/dev requirements split (Phase 7, week6-d7).

The deployed app installs only requirements.txt, so no test/lint tool may leak
into it; requirements-dev.txt must pull in the runtime set and add the dev tools.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = (ROOT / "requirements.txt").read_text(encoding="utf-8")
DEV = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
API = (ROOT / "requirements-api.txt").read_text(encoding="utf-8")


def _resolve(text: str) -> str:
    """Inline any `-r other.txt` includes, recursively.

    The runtime set is split across surfaces: shared deps live in
    requirements-base.txt, and requirements.txt (Streamlit) and
    requirements-api.txt (FastAPI) each include it. What matters to these gates
    is what a surface EFFECTIVELY installs, so the includes are followed rather
    than skipped — otherwise the split would silently defeat every assertion
    below.
    """
    out = []
    for ln in text.splitlines():
        stripped = ln.strip()
        if stripped.startswith("-r "):
            target = ROOT / stripped[3:].strip()
            out.append(_resolve(target.read_text(encoding="utf-8")))
        else:
            out.append(ln)
    return "\n".join(out)


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
        name = ln.split("==")[0].split(">=")[0].strip()
        # Strip extras: "uvicorn[standard]" is the uvicorn distribution.
        name = name.split("[")[0].strip()
        names.add(name)
    return names


def test_runtime_has_core_deps():
    names = _dep_names(_resolve(RUNTIME))
    for dep in _RUNTIME_CORE:
        assert dep in names, f"runtime requirements.txt missing {dep}"


def test_the_api_surface_excludes_presentation_dependencies():
    """The whole point of the split.

    Streamlit, PyArrow and Plotly are presentation dependencies with no business
    in a backend image, and they roughly triple its size. If one reappears here,
    the split has quietly stopped paying for itself.
    """
    names = _dep_names(_resolve(API))
    for dep in ("streamlit", "pyarrow", "plotly"):
        assert dep not in names, f"requirements-api.txt must not install {dep}"


def test_the_api_surface_has_what_it_needs():
    names = _dep_names(_resolve(API))
    for dep in ("fastapi", "uvicorn", "sqlalchemy", "anthropic"):
        assert dep in names, f"requirements-api.txt missing {dep}"


def test_pyarrow_is_pinned_to_ci_verified_version():
    """Keep Streamlit AppTest away from PyArrow 25's native crash.

    PyArrow 25 segfaults while Streamlit 1.50 converts the Journal's pandas
    frames on Python 3.11.  Version 21 is exercised by the three subprocess
    Journal interaction flows and by the full CI suite.
    """

    assert "pyarrow==21.0.0" in {
        line.strip()
        for line in RUNTIME.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def test_runtime_has_no_dev_tools():
    """Includes are resolved here too.

    Both deployed surfaces now include requirements-base.txt, so a dev tool
    added there would reach production twice over while a text-only check of
    requirements.txt saw nothing wrong.
    """
    for surface, text_ in (
        ("requirements.txt", RUNTIME),
        ("requirements-api.txt", API),
    ):
        names = _dep_names(_resolve(text_))
        for tool in _DEV_TOOLS:
            assert tool not in names, f"dev tool {tool} must not be in {surface}"


def test_dev_references_runtime():
    assert "-r requirements.txt" in DEV


def test_dev_has_all_dev_tools():
    names = _dep_names(DEV)
    for tool in _DEV_TOOLS:
        assert tool in names, f"requirements-dev.txt missing {tool}"
