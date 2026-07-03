"""
Pre-login landing page (Part 5 redesign) — rendered by `_render_login()` in
`src/tradelens/ui/components/auth.py`.

The page builders are pure string functions, so we gate the redesign's contract
directly on their HTML: a real hero value proposition, an honest no-signals scope
line, left-aligned feature highlights, one CTA, and none of the AI-aesthetic
anti-patterns the audit called out (gradient text, glassmorphism, icon-in-circle,
centered-everything). The login form itself is covered by tests/test_auth.py.
"""

from __future__ import annotations

import re

import src.tradelens.ui.components.auth as auth


def _full_html() -> str:
    return (
        auth._landing_css()
        + auth._landing_header_html()
        + auth._landing_hero_html()
        + auth._landing_features_html()
        + auth._landing_footer_html()
    )


# ---------------------------------------------------------------------------
# Content — a real landing page, not a bare login card
# ---------------------------------------------------------------------------


def test_hero_has_value_proposition():
    assert "reads your charts back to you" in auth._landing_hero_html()


def test_hero_headline_is_semantic_h1():
    assert "<h1" in auth._landing_hero_html()


def test_scope_line_is_honest_no_signals():
    hero = auth._landing_hero_html().lower()
    assert "does not generate signals" in hero


def test_three_feature_highlights_present():
    feats = auth._landing_features_html()
    assert "Screenshot-first journaling" in feats
    assert "SMC / ICT analytics" in feats
    assert "Weekly AI review" in feats


def test_single_clear_cta_and_beta_badge():
    foot = auth._landing_footer_html()
    assert "Private beta" in foot  # social-proof placeholder, not fake numbers


def test_uses_svg_icons_not_emoji():
    html = _full_html()
    assert "<svg" in html
    # No emoji pictographs used as icons anywhere on the landing.
    assert not re.search(r"[\U0001f000-\U0001faff\U00002600-\U000027bf]", html)


# ---------------------------------------------------------------------------
# Anti-patterns — the audit's P0/P1 tells must stay cleared
# ---------------------------------------------------------------------------


def test_no_centered_everything():
    # The old card centered the whole page; the redesign is left-aligned.
    assert "text-align:center" not in _full_html()


def test_no_gradient_text():
    css = auth._landing_css()
    assert "background-clip:text" not in css.replace(" ", "")
    assert "-webkit-background-clip" not in css


def test_no_glassmorphism_or_neon():
    css = auth._landing_css().lower()
    assert "backdrop-filter" not in css
    assert "blur(" not in css


def test_no_side_stripe_accent_borders():
    # Side-stripe borders (border-left/right > 1px as accent) are banned; the
    # feature blocks use a full top rule instead.
    css = auth._landing_css().lower()
    assert "border-left:" not in css.replace(" ", "")
    assert "border-right:" not in css.replace(" ", "")


def test_dark_theme_tokens_used_not_hardcoded_palette():
    # Colors come from theme.py tokens (interpolated), so the page can never drift
    # from the app shell. The accent teal appears via the token value.
    from src.tradelens.ui.components.theme import TEAL, TEXT_PRIMARY

    css = auth._landing_css()
    assert TEAL in css and TEXT_PRIMARY in css


def test_respects_reduced_motion():
    assert "prefers-reduced-motion" in auth._landing_css()


# ---------------------------------------------------------------------------
# R5 — no predictive / signal language except inside a negated disclaimer
# ---------------------------------------------------------------------------

_PREDICTIVE = ["buy signal", "sell signal", "price will", "we predict", "forecast"]
_NEGATIONS = ("not", "no ", "never", "doesn't", "does not", "without")


def test_no_predictive_language():
    low = _full_html().lower()
    for phrase in _PREDICTIVE:
        idx = low.find(phrase)
        while idx != -1:
            window = low[max(0, idx - 45) : idx]
            assert any(
                neg in window for neg in _NEGATIONS
            ), f"non-negated predictive language: {phrase!r}"
            idx = low.find(phrase, idx + 1)
