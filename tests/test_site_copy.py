"""The homepage's public promise.

One sentence has to mean the same thing on the site, the auth screen, and
in founder outreach, or the product reads as three different products.
These tests pin the category, the outcome, and the boundary — and pin the
absence of anything that sounds like a performance claim.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "site" / "index.html").read_text(encoding="utf-8")


def test_homepage_leads_with_post_trade_category_and_outcome():
    lowered = HTML.lower()
    assert "post-trade journal" in lowered
    assert "process, psychology, and performance" in lowered


def test_homepage_states_the_boundary_once_near_the_primary_story():
    assert "never tells you what to trade" in HTML.lower()


def test_homepage_does_not_promise_profit_or_prediction():
    forbidden = (
        "guaranteed returns",
        "predict the market",
        "winning trades",
        "beat the market",
        "profitable trades",
    )
    lowered = HTML.lower()
    for term in forbidden:
        assert term not in lowered, f"homepage promises {term!r}"


def test_positioning_doc_is_the_source_of_truth():
    doc = ROOT / "docs" / "business" / "positioning.md"
    assert doc.exists(), "positioning.md must exist as the canonical copy source"
    text = doc.read_text(encoding="utf-8").lower()
    for section in ("## category", "## primary promise", "## boundary"):
        assert section in text


def test_homepage_promise_matches_the_positioning_doc():
    """The doc is only useful if the page actually says what it says."""
    doc = (ROOT / "docs" / "business" / "positioning.md").read_text(encoding="utf-8")
    # Compare on content, not layout: the doc is hard-wrapped, so the promise
    # spans two source lines.
    flat_doc = " ".join(doc.split()).lower()
    promise = (
        "turns completed trades into evidence-backed reviews of your "
        "process, psychology, and performance"
    )
    assert promise in flat_doc, "positioning.md no longer states the promise"
    assert promise in " ".join(HTML.split()).lower(), "the page drifted from the doc"
