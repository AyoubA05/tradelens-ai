"""The published policies, and whether the product still backs them.

A privacy policy is a set of claims about code. The risk is not that the
page is badly written — it is that the code changes and the page quietly
becomes false. These tests tie each promise to the capability that makes
it true, so removing the capability breaks the build rather than turning
the policy into a lie.
"""

from pathlib import Path

import pytest

from scripts.build_site import BuildError, build, validate_support_email

ROOT = Path(__file__).resolve().parents[1]
PRIVACY = ROOT / "site" / "privacy" / "index.html"
TERMS = ROOT / "site" / "terms" / "index.html"

REAL = "https://www.tradelensai.io"
APP = "https://tradelenai.streamlit.app"
SUPPORT = "support@example.com"


def _text(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


# --- the pages exist and are wired -----------------------------------------


def test_both_policy_pages_exist():
    assert PRIVACY.exists()
    assert TERMS.exists()


@pytest.mark.parametrize("page", [PRIVACY, TERMS])
def test_policy_pages_use_deploy_tokens_not_hardcoded_values(page):
    text = page.read_text(encoding="utf-8")
    assert "__SITE_ORIGIN__" in text
    assert "__SUPPORT_EMAIL__" in text
    assert "tradelens-ai-site" not in text, "a deployment URL was hardcoded"


def test_the_homepage_links_to_both_policies():
    index = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    assert 'href="/privacy"' in index
    assert 'href="/terms"' in index


@pytest.mark.parametrize("page", [PRIVACY, TERMS])
def test_policy_pages_link_to_each_other(page):
    text = page.read_text(encoding="utf-8")
    assert 'href="/privacy"' in text
    assert 'href="/terms"' in text


def test_build_emits_both_pages_with_every_token_resolved(tmp_path):
    out = build(REAL, APP, SUPPORT, out=tmp_path / "site")
    for name in ("privacy", "terms"):
        html = (out / name / "index.html").read_text(encoding="utf-8")
        assert "__SITE_ORIGIN__" not in html
        assert "__SUPPORT_EMAIL__" not in html
        assert SUPPORT in html
        assert f"{REAL}/{name}" in html


# --- a contact address is mandatory ----------------------------------------


def test_a_policy_cannot_ship_without_a_contact_address(tmp_path):
    """A policy nobody can reply to is not a policy."""
    with pytest.raises(BuildError, match="SUPPORT_EMAIL"):
        build(REAL, APP, "", out=tmp_path / "site")


@pytest.mark.parametrize("bad", ["nope", "@example.com", "a@b", "a b@c.com"])
def test_a_malformed_contact_address_is_rejected(bad):
    with pytest.raises(BuildError):
        validate_support_email(bad)


# --- the promises are backed by code ---------------------------------------


def test_privacy_promises_deletion_and_the_code_provides_it():
    assert "Delete my account" in _text(PRIVACY)
    from src.tradelens.services.account import delete_account

    assert callable(delete_account)


def test_privacy_promises_export_and_the_code_provides_it():
    assert "CSV" in _text(PRIVACY)
    from src.tradelens.services.csvio import export_trades_csv

    assert callable(export_trades_csv)


def test_privacy_promises_password_reset_and_the_code_provides_it():
    from src.tradelens.services.password_reset import request_reset

    assert callable(request_reset)
    assert "resetting your password" in _text(PRIVACY)


def test_privacy_names_the_only_ai_provider_the_code_actually_calls():
    """Naming a second processor, or the wrong one, would be a false claim.

    Scoped to the AI section: Google is also named further down as the font
    host, which is a different (and true) statement.
    """
    text = _text(PRIVACY)
    section = text[
        text.index("What is sent to the AI provider") : text.index(
            "What we keep for our own records"
        )
    ]
    assert "Anthropic" in section
    for other in ("OpenAI", "Google", "Gemini", "Cohere", "Mistral", "Llama"):
        assert other not in section, f"privacy names {other} as an AI processor"

    client = (ROOT / "src" / "tradelens" / "services" / "ai_client.py").read_text(
        encoding="utf-8"
    )
    assert "anthropic" in client.lower()


def test_privacy_states_the_cost_records_that_survive_deletion():
    """delete_account keeps these; the policy must not imply total erasure."""
    from src.tradelens.services.account import ANONYMISED

    assert "ai_usage_log" in ANONYMISED
    text = _text(PRIVACY)
    assert "accounting" in text
    assert "link to your account removed" in text


# --- no overclaiming -------------------------------------------------------


def test_privacy_does_not_claim_capabilities_that_do_not_exist():
    text = _text(PRIVACY).lower()
    for claim in (
        "we back up",
        "backed up nightly",
        "encrypted at rest",
        "gdpr compliant",
        "iso 27001",
        "soc 2",
        "bank-level security",
        "military-grade",
    ):
        assert claim not in text, f"privacy page claims {claim!r}"


def test_privacy_discloses_the_gaps_rather_than_hiding_them():
    text = _text(PRIVACY)
    assert "no backups" in text.lower()
    assert "does not persist across redeployments" in text
    assert "have not undergone an external security audit" in text


def test_terms_states_the_boundary_the_whole_product_rests_on():
    text = _text(TERMS)
    assert "not financial advice" in text.lower()
    assert "does not generate trade ideas" in text


def test_terms_does_not_promise_uptime_or_recovery():
    text = _text(TERMS).lower()
    for claim in ("99.9%", "guaranteed uptime", "we will restore", "sla"):
        assert claim not in text
    assert "no uptime commitment" in text
    assert "no backups" in text


def test_neither_page_promises_trading_outcomes():
    for page in (PRIVACY, TERMS):
        text = _text(page).lower()
        for claim in ("guaranteed returns", "profitable", "beat the market"):
            assert claim not in text, f"{page.name} claims {claim!r}"
