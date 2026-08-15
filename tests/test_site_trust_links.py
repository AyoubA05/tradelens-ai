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

REAL = "https://www.tradelensai.io"
APP = "https://tradelenai.streamlit.app"
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


def _next_route_exists(route: str) -> bool:
    """Whether the Next application serves this path.

    Since Vercel's Root Directory became ``web/``, the marketing site and the
    auth routes are the same origin: this static output is served from
    ``web/public`` alongside Next's own pages. An internal link can therefore
    legitimately resolve to a Next route that this build never produces.
    """
    segment = route.strip("/")
    return (ROOT / "web" / "app" / segment / "page.tsx").exists()


def test_no_page_links_to_a_trust_destination_that_does_not_exist(tmp_path):
    """Guards the specific failure of shipping a footer link to a 404.

    The rule is unchanged — every internal link must reach something real —
    but "real" now has two forms. A link resolves either to a file this build
    wrote, or to a page the Next application serves from the same origin. A
    link matching neither is still a shipped 404, which is what this catches.
    """
    out = build(REAL, APP, SUPPORT, out=tmp_path / "site")
    for page in _PAGES:
        html = (out / page).read_text(encoding="utf-8")
        for href in re.findall(r'href="(/[^"#?]*)"', html):
            target = out / href.lstrip("/")
            resolved = target if target.suffix else target / "index.html"
            if href == "/":
                resolved = out / "index.html"
            if resolved.exists():
                continue
            assert _next_route_exists(href), (
                f"{page} links to {href}, which is neither built by the "
                f"marketing step nor served by a Next route"
            )


def test_the_journal_cta_resolves_to_a_real_next_route(tmp_path):
    """The CTA cutover depends on /login existing in the Next app.

    Asserted explicitly rather than left to the loop above, because this is
    the link the entire funnel now runs through: if web/app/login/page.tsx
    ever moves, every "Start your journal" button on the marketing site
    becomes a 404 and the product has no entry point.
    """
    out = build(REAL, APP, SUPPORT, out=tmp_path / "site")
    html = (out / "index.html").read_text(encoding="utf-8")
    assert 'href="/login"' in html
    assert _next_route_exists("/login")
    # And the route it leads to offers signup, so a new visitor is not stuck
    # on a page asking for credentials they do not have yet. The link lives in
    # the sign-in card component, which is what /login actually renders.
    card = (ROOT / "web" / "components" / "ui" / "sign-in-card-2.tsx").read_text(
        encoding="utf-8"
    )
    assert 'href="/signup"' in card
    assert (ROOT / "web" / "app" / "signup" / "page.tsx").exists()
