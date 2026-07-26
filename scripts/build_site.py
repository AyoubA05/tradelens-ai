"""Resolve the marketing site's deploy-time placeholders into a publishable copy.

    SITE_ORIGIN=https://www.tradelensai.io \
        APP_ORIGIN=https://tradelens-app.streamlit.app \
        python -m scripts.build_site

Copies site/ to dist/site/ with __SITE_ORIGIN__ replaced by SITE_ORIGIN. The
source tree keeps the token so it stays obviously unresolved; only the build
output is publishable.

Why a build step for a static site: the absolute URLs in <head> (canonical,
og:url, og:image, twitter:image, JSON-LD) must be absolute to work at all, so
they cannot be relative paths, and a hand-edited domain is exactly what got
forgotten before. Validation lives here so a bad origin fails the build rather
than surfacing as crawlers indexing a nonexistent host.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "site"
OUT = ROOT / "dist" / "site"

SITE_TOKEN = "__SITE_ORIGIN__"
APP_TOKEN = "__APP_ORIGIN__"
SUPPORT_TOKEN = "__SUPPORT_EMAIL__"
TOKEN = SITE_TOKEN  # back-compat for existing importers

# Substituted into text assets only; binary assets are copied verbatim.
_TEXT_SUFFIXES = {".html", ".css", ".js", ".json", ".webmanifest", ".xml", ".txt"}

# Origins that are syntactically fine but are not a real production host. These
# are the failure modes that shipped or nearly shipped before.
_REJECTED_HOST_SUFFIXES = (".example", ".invalid", ".localhost", ".test")


class BuildError(RuntimeError):
    """The build cannot produce a publishable artifact."""


def validate_origin(origin: str, name: str = "SITE_ORIGIN") -> str:
    """Return the normalized origin, or raise BuildError explaining the problem."""
    if not origin:
        raise BuildError(
            f"{name} is not set. Pass the real production origin, e.g. "
            f"{name}=https://www.tradelensai.io"
        )

    origin = origin.rstrip("/")
    parsed = urlparse(origin)

    if parsed.scheme != "https":
        raise BuildError(
            f"{name} must use https (got {parsed.scheme or 'no scheme'!r}). "
            f"og:image over http is rejected by several social platforms."
        )
    if not parsed.hostname:
        raise BuildError(f"{name} has no host: {origin!r}")
    if parsed.path:
        raise BuildError(
            f"{name} must be an origin with no path (got path {parsed.path!r}). "
            f"Paths are appended by the template."
        )

    host = parsed.hostname.lower()
    if host.endswith(_REJECTED_HOST_SUFFIXES) or host == "localhost":
        raise BuildError(
            f"{name} {host!r} is a reserved/placeholder host, not a real "
            f"production origin. This is the exact mistake the token exists to catch."
        )
    if "." not in host:
        raise BuildError(f"{name} host {host!r} is not a fully-qualified domain.")

    return origin


def validate_support_email(address: str) -> str:
    """A published policy needs a real way to reach a human.

    Validated here rather than typed into the page, because an address
    nobody reads is worse than no policy at all.
    """
    address = (address or "").strip()
    if not address:
        raise BuildError(
            "SUPPORT_EMAIL is not set. The privacy and terms pages must carry "
            "a contact address that is actually monitored."
        )
    local, _, domain = address.partition("@")
    if not local or "." not in domain or " " in address:
        raise BuildError(f"SUPPORT_EMAIL is not a valid address: {address!r}")
    return address


def build(
    site_origin: str,
    app_origin: str,
    support_email: str = "",
    src: Path = SRC,
    out: Path = OUT,
) -> Path:
    """Write the resolved site to `out` and return that path.

    Both origins are deploy inputs. The app URL used to be hardcoded in six
    places across two files, so moving the app meant editing all six by hand
    and silently keeping the old host wherever one was missed.
    """
    site_origin = validate_origin(site_origin)
    app_origin = validate_origin(app_origin, name="APP_ORIGIN")
    support_email = validate_support_email(support_email)

    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(src, out)

    replacements = {
        SITE_TOKEN: site_origin,
        APP_TOKEN: app_origin,
        SUPPORT_TOKEN: support_email,
    }

    for path in out.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8")
        new_text = text
        for token, value in replacements.items():
            new_text = new_text.replace(token, value)
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")

    leftover = [
        str(p.relative_to(out))
        for p in out.rglob("*")
        if p.is_file()
        and p.suffix.lower() in _TEXT_SUFFIXES
        and any(t in p.read_text(encoding="utf-8") for t in replacements)
    ]
    if leftover:  # pragma: no cover — defensive; substitution above is total
        raise BuildError(f"deploy token survived in: {', '.join(leftover)}")

    return out


def main() -> int:
    try:
        out = build(
            os.getenv("SITE_ORIGIN", ""),
            os.getenv("APP_ORIGIN", ""),
            os.getenv("SUPPORT_EMAIL", ""),
        )
    except BuildError as exc:
        print(f"build_site: {exc}", file=sys.stderr)
        return 1
    print(f"build_site: wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
