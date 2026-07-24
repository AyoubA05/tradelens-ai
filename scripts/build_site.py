"""Resolve the marketing site's deploy-time placeholders into a publishable copy.

    SITE_ORIGIN=https://www.tradelens-ai.com python -m scripts.build_site

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

TOKEN = "__SITE_ORIGIN__"

# Substituted into text assets only; binary assets are copied verbatim.
_TEXT_SUFFIXES = {".html", ".css", ".js", ".json", ".webmanifest", ".xml", ".txt"}

# Origins that are syntactically fine but are not a real production host. These
# are the failure modes that shipped or nearly shipped before.
_REJECTED_HOST_SUFFIXES = (".example", ".invalid", ".localhost", ".test")


class BuildError(RuntimeError):
    """The build cannot produce a publishable artifact."""


def validate_origin(origin: str) -> str:
    """Return the normalized origin, or raise BuildError explaining the problem."""
    if not origin:
        raise BuildError(
            "SITE_ORIGIN is not set. Pass the real production origin, e.g. "
            "SITE_ORIGIN=https://www.tradelens-ai.com"
        )

    origin = origin.rstrip("/")
    parsed = urlparse(origin)

    if parsed.scheme != "https":
        raise BuildError(
            f"SITE_ORIGIN must use https (got {parsed.scheme or 'no scheme'!r}). "
            f"og:image over http is rejected by several social platforms."
        )
    if not parsed.hostname:
        raise BuildError(f"SITE_ORIGIN has no host: {origin!r}")
    if parsed.path:
        raise BuildError(
            f"SITE_ORIGIN must be an origin with no path (got path {parsed.path!r}). "
            f"Paths are appended by the template."
        )

    host = parsed.hostname.lower()
    if host.endswith(_REJECTED_HOST_SUFFIXES) or host == "localhost":
        raise BuildError(
            f"SITE_ORIGIN {host!r} is a reserved/placeholder host, not a real "
            f"production origin. This is the exact mistake the token exists to catch."
        )
    if "." not in host:
        raise BuildError(f"SITE_ORIGIN host {host!r} is not a fully-qualified domain.")

    return origin


def build(origin: str, src: Path = SRC, out: Path = OUT) -> Path:
    """Write the resolved site to `out` and return that path."""
    origin = validate_origin(origin)

    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(src, out)

    for path in out.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8")
        if TOKEN in text:
            path.write_text(text.replace(TOKEN, origin), encoding="utf-8")

    leftover = [
        str(p.relative_to(out))
        for p in out.rglob("*")
        if p.is_file()
        and p.suffix.lower() in _TEXT_SUFFIXES
        and TOKEN in p.read_text(encoding="utf-8")
    ]
    if leftover:  # pragma: no cover — defensive; substitution above is total
        raise BuildError(f"{TOKEN} survived substitution in: {', '.join(leftover)}")

    return out


def main() -> int:
    try:
        out = build(os.getenv("SITE_ORIGIN", ""))
    except BuildError as exc:
        print(f"build_site: {exc}", file=sys.stderr)
        return 1
    print(f"build_site: wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
