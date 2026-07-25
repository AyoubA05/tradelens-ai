"""Check that an anonymous visitor can actually reach TradeLens.

Two deployment-side failures shipped together and neither was visible from
the repository:

  * the canonical domain served an older, differently-positioned build;
  * the app URL bounced anonymous visitors into Streamlit's own provider
    login instead of TradeLens's auth screen.

Both look fine locally, so this checks the live hosts. Standard library
only, read-only, no dependencies.

    python scripts/verify_public_funnel.py \
        --site https://tradelens-ai.com \
        --app https://tradelens-app.streamlit.app

Exit code 0 only when every check passes.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass

# The title the current marketing build serves. A different one means the
# domain is pointed at another deployment, which is exactly what happened.
EXPECTED_TITLE = "TradeLens AI — Post-Trade Journal. AI-Powered Growth."

# URL fragments that mean the visitor landed on someone else's login wall
# rather than on TradeLens.
_PROVIDER_AUTH_MARKERS = (
    "/sso-api",
    "share.streamlit.io/-/auth",
    "/-/login",
    "vercel.com/login",
)

_TIMEOUT_S = 20
_UA = "TradeLens-funnel-check/1.0"


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    url: str
    detail: str = ""


def _title_of(html: str) -> str | None:
    lowered = html.lower()
    start = lowered.find("<title>")
    if start == -1:
        return None
    end = lowered.find("</title>", start)
    if end == -1:
        return None
    return html[start + len("<title>") : end].strip()


def classify(
    status: int, final_url: str, html: str, *, expect_title: bool = True
) -> CheckResult:
    """Decide whether a fetched endpoint represents a working public entry.

    `final_url` is the URL *after* redirects — that is where a provider
    login wall becomes visible.
    """
    lowered_url = final_url.lower()
    if any(marker in lowered_url for marker in _PROVIDER_AUTH_MARKERS):
        return CheckResult(
            False,
            final_url,
            f"landed on provider authentication ({final_url}); anonymous "
            f"visitors never reach TradeLens",
        )

    if status != 200:
        return CheckResult(False, final_url, f"HTTP {status}")

    if expect_title:
        title = _title_of(html)
        # &amp; survives in raw HTML; compare on the decoded form.
        normalised = (title or "").replace("&amp;", "&")
        if normalised != EXPECTED_TITLE:
            return CheckResult(
                False,
                final_url,
                f"unexpected title {title!r} — expected {EXPECTED_TITLE!r}; "
                f"the domain is serving a different build",
            )

    return CheckResult(True, final_url)


def check_endpoint(url: str, *, expect_title: bool = True) -> CheckResult:
    """Fetch `url` and classify it. Never raises for network problems."""
    request = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:
            body = response.read(200_000).decode("utf-8", errors="replace")
            return classify(
                response.status,
                response.geturl(),
                body,
                expect_title=expect_title,
            )
    except urllib.error.HTTPError as exc:
        # urllib surfaces a cross-host 303 as an error rather than following
        # it. The Location header still names the destination, and that
        # destination is the whole point of this check.
        location = exc.headers.get("Location") if exc.headers else None
        if 300 <= exc.code < 400 and location:
            return classify(200, location, "", expect_title=False)
        return classify(exc.code, exc.url or url, "", expect_title=expect_title)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return CheckResult(False, url, f"request failed: {exc}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", required=True, help="public marketing origin")
    parser.add_argument("--app", required=True, help="public app origin")
    args = parser.parse_args(argv)

    checks = (
        ("marketing", check_endpoint(args.site)),
        ("app", check_endpoint(args.app, expect_title=False)),
    )

    failed = False
    for name, result in checks:
        if result.ok:
            print(f"PASS  {name}: {result.url}")
        else:
            failed = True
            print(f"FAIL  {name}: {result.detail}", file=sys.stderr)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
