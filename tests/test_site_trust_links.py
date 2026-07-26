"""The trust destinations a visitor can actually reach from the site.

The audit's finding was that the site made privacy-adjacent claims with no
public policy behind them. The fix is not only that the pages exist, but
that they are reachable from every page and that the links resolve to real
files rather than to a plausible-looking 404.

The support address is a build token, so the source is checked for the
token and the built output for a real address. Asserting a literal address
in source would just re-introduce the hardcoding the token removed.
"""

import re
from pathlib import Path

import pytest

from scripts.build_site import build

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"

REAL = "https://www.tradelens-ai.com"
APP = "https://tradelens-app.streamlit.app"
SUPPORT = "support@example.com"

# Every page a visitor can land on must offer the same routes out.
_PAGES = ("index.html", "privacy/index.html", "terms/index.html")


def _source(page: str) -> str:
    return (SITE / page).read_text(encoding="utf-8")


@pytest.mark.parametrize("page", _PAGES)
def test_every_page_links_to_privacy_terms_and_support(page):
    html = _source(page)
    assert 'href="/privacy"' in html, f"{page} does not link to /privacy"
    assert 'href="/terms"' in html, f"{page} does not link to /terms"
    assert 'href="mailto:__SUPPORT_EMAIL__"' in html, f"{page} has no support route"


# An address, not merely an "@": the markup legitimately contains @media,
# @font-face, and a `satoshi@400,500,700` font query.
_EMAIL_SHAPED = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def test_support_is_a_token_not_a_hardcoded_address():
    """The address lives in one deploy input, not scattered through markup."""
    for page in _PAGES:
        source = _source(page).replace("__SUPPORT_EMAIL__", "")
        found = _EMAIL_SHAPED.findall(source)
        assert not found, f"{page} hardcodes an address: {found}"


def test_the_built_site_serves_those_destinations(tmp_path):
    """A link to /privacy is only a trust signal if a file answers it."""
    out = build(REAL, APP, SUPPORT, out=tmp_path / "site")
    assert (out / "privacy" / "index.html").is_file()
    assert (out / "terms" / "index.html").is_file()


def test_built_links_resolve_to_a_real_support_address(tmp_path):
    out = build(REAL, APP, SUPPORT, out=tmp_path / "site")
    for page in _PAGES:
        html = (out / page).read_text(encoding="utf-8")
        assert f'href="mailto:{SUPPORT}"' in html
        assert "__SUPPORT_EMAIL__" not in html


def test_no_page_links_to_a_trust_destination_that_does_not_exist(tmp_path):
    """Guards the specific failure of shipping a footer link to a 404."""
    out = build(REAL, APP, SUPPORT, out=tmp_path / "site")
    for page in _PAGES:
        html = (out / page).read_text(encoding="utf-8")
        for href in re.findall(r'href="(/[^"#?]*)"', html):
            target = out / href.lstrip("/")
            resolved = target if target.suffix else target / "index.html"
            if href == "/":
                resolved = out / "index.html"
            assert resolved.exists(), f"{page} links to {href}, which is not built"
