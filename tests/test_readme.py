"""
Doc-asset gates (Phase 6, week6-d6): README structure, demo script beats, and
resume bullets. These assert the portfolio docs stay complete and that no real
screenshot URLs sneak in before the post-deploy screenshot pass.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
DEMO_SCRIPT = ROOT / "docs" / "DEMO_SCRIPT.md"
RESUME = ROOT / "docs" / "RESUME_BULLETS.md"

# One marker per required section (a–k from the Phase 6 spec).
_REQUIRED_SECTION_MARKERS = [
    "shields.io",  # a. badges row
    "post-trade reflection journal",  # b. one-line pitch
    "<!-- screenshot: dashboard",  # c. hero screenshot placeholder
    "## What makes TradeLens different",  # d.
    "## Architecture",  # e.
    "## Features",  # f.
    "## Quickstart",  # g.
    "## AI Prompt Architecture",  # h.
    "## Demo Mode",  # i.
    "## Roadmap",  # j.
    "## License",  # k.
]


def test_readme_has_required_sections():
    text = README.read_text(encoding="utf-8")
    for marker in _REQUIRED_SECTION_MARKERS:
        assert marker in text, f"README missing required section marker: {marker!r}"


def test_readme_no_real_screenshot_urls():
    """All images must be placeholders; no markdown image links to real URLs."""
    text = README.read_text(encoding="utf-8")
    assert not re.search(
        r"!\[[^\]]*\]\(http", text
    ), "README has a real markdown image link — use <!-- screenshot: ... --> placeholders"


def test_readme_has_mermaid_diagram():
    assert "```mermaid" in README.read_text(encoding="utf-8")


def test_readme_has_ai_prompt_architecture():
    assert "AI Prompt Architecture" in README.read_text(encoding="utf-8")


def test_demo_script_has_six_beats():
    text = DEMO_SCRIPT.read_text(encoding="utf-8")
    for marker in ("0:00", "0:10", "0:25", "0:40", "0:55", "1:10", "1:25"):
        assert marker in text, f"DEMO_SCRIPT missing beat marker: {marker}"


def test_resume_bullets_has_five_bullets():
    bullets = [
        ln
        for ln in RESUME.read_text(encoding="utf-8").splitlines()
        if ln.startswith("- ")
    ]
    assert len(bullets) == 5, f"expected 5 resume bullets, found {len(bullets)}"


def test_resume_bullets_mentions_required_terms():
    text = RESUME.read_text(encoding="utf-8")
    for term in ("claude-fable-5", "474", "92%", "Alembic", "SMC/ICT", "few-shot"):
        assert term in text, f"RESUME_BULLETS missing required term: {term!r}"
