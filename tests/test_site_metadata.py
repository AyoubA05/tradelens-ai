"""The marketing site's deploy-time origin substitution.

SP1 shipped absolute canonical/OG/JSON-LD URLs pointing at the placeholder
origin `https://www.tradelens-ai.example`. Deployed unchanged, that sends
crawlers to a nonexistent host and stops social platforms fetching the preview
image — and nothing in the build would have complained, because a .example URL
is perfectly well-formed.

These tests replace "remember to swap the domain" with a failing build.
"""

from pathlib import Path

import pytest

from scripts.build_site import TOKEN, BuildError, build, validate_origin

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "site" / "index.html"

REAL = "https://www.tradelens-ai.com"
APP = "https://tradelens-app.streamlit.app"
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
        validate_origin("http://www.tradelens-ai.com")


def test_origin_with_path_is_rejected():
    with pytest.raises(BuildError, match="no path"):
        validate_origin("https://www.tradelens-ai.com/site")


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


def test_source_uses_app_origin_token():
    text = _index_text()
    assert "__APP_ORIGIN__" in text
    assert APP not in text


def test_main_js_uses_app_origin_token():
    js = (ROOT / "site" / "main.js").read_text(encoding="utf-8")
    assert "__APP_ORIGIN__" in js
    assert APP not in js


def test_build_resolves_site_and_app_origins(tmp_path):
    out = build(REAL, APP, SUPPORT, out=tmp_path / "site")
    html = (out / "index.html").read_text(encoding="utf-8")
    js = (out / "main.js").read_text(encoding="utf-8")
    assert "__SITE_ORIGIN__" not in html
    assert "__APP_ORIGIN__" not in html + js
    assert f'href="{APP}"' in html
    assert f'const APP_URL = "{APP}"' in js


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
