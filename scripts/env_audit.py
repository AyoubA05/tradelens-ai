"""Presence-and-shape audit of the authentication environment.

Prints a verdict per setting and never a value. That is the whole design
constraint: this runs in terminals whose output ends up in transcripts and
issue threads, so a connection string, invite code or SMTP password must not be
reconstructible from what it says — not even in an error message.

Verdicts:
    PRESENT   set, and passes the shape check for that setting
    MISSING   not set
    INVALID   set but cannot be what it claims to be
"""

from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

# Settings the website reads. TRADELENS_SESSION_SECRET is deliberately absent:
# nothing in web/ reads it, and listing it would resurrect a dead requirement.
WEBSITE = [
    "DATABASE_URL",
    "SITE_ORIGIN",
    "APP_ORIGIN",
    "SIGNUP_MODE",
    "TRADELENS_INVITE_CODE",
    "TRADELENS_SMTP_HOST",
    "TRADELENS_SMTP_PORT",
    "TRADELENS_SMTP_USER",
    "TRADELENS_SMTP_PASSWORD",
    "TRADELENS_SMTP_FROM",
]

STREAMLIT = [
    "DATABASE_URL",
    "SITE_ORIGIN",
    "ANTHROPIC_API_KEY",
    # Legacy login only. Retires with it.
    "TRADELENS_SESSION_SECRET",
    "TRADELENS_USERNAME",
    "TRADELENS_PASSWORD",
]

SENSITIVE = {
    "DATABASE_URL",
    "TRADELENS_INVITE_CODE",
    "TRADELENS_SMTP_PASSWORD",
    "TRADELENS_SESSION_SECRET",
    "TRADELENS_PASSWORD",
    "ANTHROPIC_API_KEY",
}


def _origin_verdict(value: str, *, allow_local: bool) -> tuple[str, str]:
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return "INVALID", "not an absolute http(s) origin"
    if parsed.path not in ("", "/"):
        return "INVALID", "carries a path; must be scheme://host[:port] only"
    host = (parsed.hostname or "").lower()
    local = host in ("localhost", "127.0.0.1", "::1")
    if parsed.scheme == "http":
        if not local:
            return "INVALID", "http:// is only allowed for loopback"
        if not allow_local:
            return "INVALID", "loopback origin outside local development"
        return "PRESENT", "http, loopback — local development exception"
    return "PRESENT", "https"


def _verdict(name: str, value: str | None, *, allow_local: bool) -> tuple[str, str]:
    if not value:
        return "MISSING", ""

    if name in ("SITE_ORIGIN", "APP_ORIGIN"):
        return _origin_verdict(value, allow_local=allow_local)

    if name == "DATABASE_URL":
        parsed = urlparse(value)
        if parsed.scheme.split("+")[0] not in ("postgresql", "postgres", "sqlite"):
            return "INVALID", "unrecognised database scheme"
        if parsed.scheme.startswith("sqlite"):
            return "PRESENT", "sqlite — local only"
        if "sslmode=require" not in value and "sslmode=verify" not in value:
            return "INVALID", "postgres URL without sslmode=require"
        return "PRESENT", "postgresql, sslmode required"

    if name == "SIGNUP_MODE":
        if value not in ("invite", "open", "closed"):
            return "INVALID", "must be invite | open | closed (unknown fails closed)"
        return "PRESENT", value

    if name == "TRADELENS_SMTP_PORT":
        if not value.isdigit() or not (0 < int(value) < 65536):
            return "INVALID", "not a port number"
        return "PRESENT", f"port {value}"

    if name == "TRADELENS_SMTP_FROM":
        if "@" not in value:
            return "INVALID", "not an address"
        return "PRESENT", ""

    if name == "TRADELENS_INVITE_CODE":
        return (
            ("PRESENT", "") if len(value) >= 8 else ("INVALID", "shorter than 8 chars")
        )

    if name == "TRADELENS_SESSION_SECRET":
        return (
            ("PRESENT", "")
            if len(value) >= 32
            else ("INVALID", "shorter than 32 chars")
        )

    return "PRESENT", ""


def audit(surface: str, names: list, *, allow_local: bool) -> int:
    print(f"\n{surface}")
    problems = 0
    for name in names:
        verdict, note = _verdict(name, os.environ.get(name), allow_local=allow_local)
        if verdict == "INVALID":
            problems += 1
        marker = "!" if verdict == "INVALID" else " "
        label = f"{name} [sensitive]" if name in SENSITIVE else name
        print(f"  {marker} {label:<42} {verdict}" + (f"  ({note})" if note else ""))
    return problems


def cross_checks(*, allow_local: bool) -> int:
    """Catches the configuration mistakes that presence checks cannot see."""
    print("\nCROSS-CHECKS")
    problems = 0
    site = os.environ.get("SITE_ORIGIN", "")
    app = os.environ.get("APP_ORIGIN", "")

    if site and app:
        same = site.rstrip("/").lower() == app.rstrip("/").lower()
        print(
            f"  {'!' if same else ' '} SITE_ORIGIN and APP_ORIGIN differ    "
            f"{'FAIL — they are interchangeable' if same else 'OK'}"
        )
        problems += int(same)

        # The one that actually bites: swapping them sends verification and
        # reset links to the Streamlit host, which has no route to consume them.
        looks_swapped = "streamlit" in site.lower() and "streamlit" not in app.lower()
        print(
            f"  {'!' if looks_swapped else ' '} SITE_ORIGIN is not the app host     "
            f"{'FAIL — looks swapped' if looks_swapped else 'OK'}"
        )
        problems += int(looks_swapped)

    if not allow_local:
        for name in ("SITE_ORIGIN", "APP_ORIGIN"):
            value = os.environ.get(name, "")
            bad = value.startswith("http://")
            print(
                f"  {'!' if bad else ' '} {name} uses HTTPS in production   "
                f"{'FAIL' if bad else 'OK'}"
            )
            problems += int(bad)

    host = os.environ.get("TRADELENS_SMTP_HOST", "")
    from_addr = os.environ.get("TRADELENS_SMTP_FROM", "")
    configured = bool(host and from_addr)
    print(
        f"    outbound mail configured              "
        f"{'yes' if configured else 'no — the app reports unavailable, never sent'}"
    )

    return problems


def main() -> int:
    allow_local = "--local" in sys.argv
    print("AUTH ENVIRONMENT AUDIT" + ("  (local development)" if allow_local else ""))
    print("Values are never printed.")
    problems = audit("WEBSITE (Vercel / web)", WEBSITE, allow_local=allow_local)
    problems += audit("STREAMLIT (app)", STREAMLIT, allow_local=allow_local)
    problems += cross_checks(allow_local=allow_local)
    print(
        f"\n{'AUDIT PASSED' if problems == 0 else f'AUDIT FOUND {problems} PROBLEM(S)'}"
    )
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
