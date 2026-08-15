"""The marketing site's deploy-time origin substitution.

SP1 shipped absolute canonical/OG/JSON-LD URLs pointing at the placeholder
origin `https://www.tradelens-ai.example`. Deployed unchanged, that sends
crawlers to a nonexistent host and stops social platforms fetching the preview
image — and nothing in the build would have complained, because a .example URL
is perfectly well-formed.

These tests replace "remember to swap the domain" with a failing build.
"""

import re
from pathlib import Path

import pytest

from scripts.build_site import TOKEN, BuildError, build, validate_origin

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "site" / "index.html"

REAL = "https://www.tradelensai.io"
APP = "https://tradelenai.streamlit.app"
SUPPORT = "support@example.com"

# The <head> fields that must carry an absolute production URL.
_ABSOLUTE_URL_FIELDS = (
    'rel="canonical"',
    'property="og:url"',
    'property="og:image"',
    'name="twitter:image"',
)


def _index_text() -> str:
    return INDEX.read_text(encoding="utf-8")


# --- the source tree ------------------------------------------------------


def test_source_contains_no_placeholder_domain():
    """Regression: the .example origin must not reappear in source."""
    assert ".example" not in _index_text()


def test_source_uses_the_token_for_absolute_urls():
    text = _index_text()
    for field in _ABSOLUTE_URL_FIELDS:
        line = next(ln for ln in text.splitlines() if field in ln)
        assert TOKEN in line, f"{field} must use {TOKEN}, got: {line.strip()}"


def test_json_ld_url_uses_the_token():
    line = next(ln for ln in _index_text().splitlines() if "application/ld+json" in ln)
    assert TOKEN in line


# --- origin validation ----------------------------------------------------


def test_valid_origin_is_accepted():
    assert validate_origin(REAL) == REAL


def test_trailing_slash_is_normalized():
    """The template supplies the slash, so a trailing one would double it."""
    assert validate_origin(REAL + "/") == REAL


def test_missing_origin_is_rejected():
    with pytest.raises(BuildError, match="not set"):
        validate_origin("")


@pytest.mark.parametrize(
    "origin",
    [
        "https://www.tradelens-ai.example",
        "https://tradelens.invalid",
        "https://localhost",
        "https://app.localhost",
    ],
)
def test_placeholder_hosts_are_rejected(origin):
    """The precise class of value that caused the original finding."""
    with pytest.raises(BuildError):
        validate_origin(origin)


def test_http_origin_is_rejected():
    with pytest.raises(BuildError, match="https"):
        validate_origin("http://www.tradelensai.io")


def test_origin_with_path_is_rejected():
    with pytest.raises(BuildError, match="no path"):
        validate_origin("https://www.tradelensai.io/site")


def test_bare_hostname_is_rejected():
    with pytest.raises(BuildError, match="fully-qualified"):
        validate_origin("https://tradelens")


# --- the build output -----------------------------------------------------


def test_build_resolves_every_token(tmp_path):
    out = build(REAL, APP, SUPPORT, out=tmp_path / "site")
    html = (out / "index.html").read_text(encoding="utf-8")
    assert TOKEN not in html
    assert ".example" not in html
    assert f'href="{REAL}/"' in html
    assert f'content="{REAL}/assets/og-image.png"' in html


def test_build_output_has_absolute_urls_on_every_required_field(tmp_path):
    out = build(REAL, APP, SUPPORT, out=tmp_path / "site")
    html = (out / "index.html").read_text(encoding="utf-8")
    for field in _ABSOLUTE_URL_FIELDS:
        line = next(ln for ln in html.splitlines() if field in ln)
        assert REAL in line, f"{field} lost its absolute origin: {line.strip()}"


def test_build_copies_binary_assets_intact(tmp_path):
    """Substitution must not corrupt images it walks past."""
    out = build(REAL, APP, SUPPORT, out=tmp_path / "site")
    src_assets = ROOT / "site" / "assets"
    for asset in src_assets.glob("*.png"):
        assert (out / "assets" / asset.name).read_bytes() == asset.read_bytes()


def test_build_refuses_a_placeholder_origin(tmp_path):
    with pytest.raises(BuildError):
        build("https://www.tradelens-ai.example", APP, SUPPORT, out=tmp_path / "site")


def test_build_is_repeatable(tmp_path):
    """A second build over an existing output directory must not accumulate state."""
    out = tmp_path / "site"
    build(REAL, APP, SUPPORT, out=out)
    first = (out / "index.html").read_text(encoding="utf-8")
    build(REAL, APP, SUPPORT, out=out)
    assert (out / "index.html").read_text(encoding="utf-8") == first


# ---------------------------------------------------------------------------
# The app origin is the second deploy input
# ---------------------------------------------------------------------------
#
# The app URL was hardcoded in six places across two files. A move (custom
# domain, staging host) meant editing all six by hand, and the site would
# silently keep pointing at the old host wherever one was missed.


def test_journal_ctas_route_through_the_website_login():
    """The CTA cutover: no marketing link goes straight to the app.

    Every "Start your journal" button used to carry `data-app-link` and an
    `__APP_ORIGIN__` href, and main.js rewrote them to the Streamlit host at
    runtime. Arriving there without a handoff credential lands on the legacy
    login screen, which skips the website auth flow — signup, verification,
    the session cookie and the one-time handoff — entirely.

    They now point at `/login`, relatively. Same origin since Vercel's Root
    Directory became web/, so no build token is involved and nothing can
    rewrite them.
    """
    text = _index_text()
    ctas = re.findall(r"<a[^>]*data-cta-location=\"([a-z]+)\"[^>]*>", text)
    assert sorted(ctas) == ["final", "hero", "mobile", "nav", "pricing"]

    for match in re.finditer(r"<a([^>]*data-cta-location=[^>]*)>", text):
        tag = match.group(1)
        assert 'href="/login"' in tag, tag
        assert "data-app-link" not in tag, tag
        assert "__APP_ORIGIN__" not in tag, tag

    # And the token is gone from the page altogether.
    assert "__APP_ORIGIN__" not in text
    assert APP not in text


def test_no_marketing_page_links_directly_to_the_app_host():
    for page in ("index.html", "privacy/index.html", "terms/index.html"):
        html = (ROOT / "site" / page).read_text(encoding="utf-8")
        assert APP not in html, page
        assert "streamlit.app" not in html, page


def test_no_repository_vercel_json_can_override_the_deployment():
    """The deployment configuration lives in one place, and it is not here.

    A root ``vercel.json`` used to describe the marketing-only build: a no-op
    install command, ``python3 scripts/build_site.py``, and ``dist/site`` as the
    output. Once Vercel's Root Directory moved to ``web/``, that file described
    a deployment that no longer exists, and it stayed in the repository as a
    loaded gun — anything that read it would run a Python static build against
    a Next.js application and fail.

    It did fire, though for a related reason: a *redeploy* replays the original
    deployment's resolved settings, so re-running the last marketing build under
    the new Root Directory produced
    ``python3: can't open file '/vercel/path0/web/scripts/build_site.py'``.

    Deleting the file is correct whichever way Vercel resolves configuration.
    If it reads ``vercel.json`` from the Root Directory, the root file was
    already ignored and nothing changes. If it reads from the repository root,
    the stale override is gone. There is deliberately no ``web/vercel.json``
    either: Next.js is auto-detected from ``web/package.json``, the build is
    ``npm run build`` — which is what runs ``prebuild`` and therefore the
    marketing step — and the response headers live in ``next.config.mjs``.
    Adding a config file to restate defaults would only create a second place
    for them to drift.
    """
    assert not (ROOT / "vercel.json").exists(), (
        "a root vercel.json is back; it describes a deployment that no longer "
        "exists and can override the web/ build"
    )
    assert not (
        ROOT / "web" / "vercel.json"
    ).exists(), "web/vercel.json is not needed — see this test's docstring"


def test_main_js_no_longer_rewrites_cta_targets():
    """Nothing may repoint a CTA at runtime.

    The markup is now the single source of truth for where a CTA goes; a
    script that rewrote hrefs is exactly how the destination got out of step
    with the auth design in the first place.
    """
    js = (ROOT / "site" / "main.js").read_text(encoding="utf-8")
    code = "\n".join(
        line
        for line in js.splitlines()
        if not line.strip().startswith(("*", "/*", "//"))
    )
    assert "data-app-link" not in code
    assert "APP_URL" not in code
    assert "__APP_ORIGIN__" not in code
    assert APP not in code


def test_cta_analytics_labels_are_preserved():
    """The cutover changed the destination, not the measurement."""
    js = (ROOT / "site" / "main.js").read_text(encoding="utf-8")
    assert "data-cta-location" in js
    assert "marketing_cta_click" in js


def test_build_resolves_site_and_app_origins(tmp_path):
    out = build(REAL, APP, SUPPORT, out=tmp_path / "site")
    html = (out / "index.html").read_text(encoding="utf-8")
    js = (out / "main.js").read_text(encoding="utf-8")
    assert "__SITE_ORIGIN__" not in html
    assert "__APP_ORIGIN__" not in html + js
    # The built output must not carry the app host either: the CTAs are
    # relative /login links now.
    assert APP not in html
    assert 'href="/login"' in html


def test_missing_app_origin_is_rejected(tmp_path):
    with pytest.raises(BuildError, match="APP_ORIGIN"):
        build(REAL, "", SUPPORT, out=tmp_path / "site")


def test_placeholder_app_origin_is_rejected(tmp_path):
    with pytest.raises(BuildError, match="APP_ORIGIN"):
        build(REAL, "https://app.example", SUPPORT, out=tmp_path / "site")


# ---------------------------------------------------------------------------
# The feature section is editorial, not a bento grid
# ---------------------------------------------------------------------------
#
# Six rounded cards, each with an icon in a tinted container and a small
# screenshot, is the first place the site reads as generated rather than
# authored. Three stories with large product proof replace them.


def test_feature_section_uses_editorial_stories_not_bento_cards():
    html = _index_text()
    assert html.count('class="story"') == 3
    assert "feature-grid" not in html
    assert "card-icon" not in html


def test_stories_each_carry_one_large_screenshot():
    html = _index_text()
    assert html.count('class="story-proof"') == 3


def test_stories_have_captions_that_say_what_the_trader_learns():
    html = _index_text()
    assert html.count("<figcaption") == 3


# ---------------------------------------------------------------------------
# Conversion measurement carries no personal data
# ---------------------------------------------------------------------------


def test_every_primary_cta_is_labelled_with_its_location():
    """Five entry points; without labels the funnel can't be diagnosed."""
    html = _index_text()
    assert html.count("data-cta-location=") == 5
    for location in ("nav", "hero", "pricing", "final", "mobile"):
        assert f'data-cta-location="{location}"' in html


def test_analytics_never_reference_personal_fields():
    """The site may measure which CTA was used, never who used it."""
    js = (ROOT / "site" / "main.js").read_text(encoding="utf-8").lower()
    for term in (
        "password",
        "username",
        "email",
        "trade_date",
        "pnl",
        "p&l",
        "notes",
        "screenshot",
        "psychology",
    ):
        assert term not in js, f"main.js references {term!r}"


def test_tracked_events_are_the_two_expected_ones():
    js = (ROOT / "site" / "main.js").read_text(encoding="utf-8")
    assert 'track("marketing_cta_click"' in js
    assert 'track("faq_open"' in js
