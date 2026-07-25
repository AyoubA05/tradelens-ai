"""Check that an anonymous visitor can actually reach TradeLens.

The two endpoints have different contracts.

**Marketing must be public.** An anonymous visitor has to see the current
build with no login wall in front of it. Both halves of that have failed
before: a canonical domain quietly serving an older, differently
positioned build, and deployment protection hiding the site behind an
SSO page. Neither is visible from the repository.

**The app is gated on purpose.** A sign-in wall is correct behaviour, so
it is not reported as a failure. What must still hold is that the gate
*routes back*: the redirect has to carry a destination pointing at this
app, so signing in returns the visitor to TradeLens. A redirect that
drops the destination, sends the visitor to a different app, or a host
that is simply down, is a real failure.

Standard library only, read-only, no dependencies.

    python scripts/verify_public_funnel.py \
        --site https://tradelens-ai-site-git-main-ayouba05s-projects.vercel.app \
        --app https://tradelens-app.streamlit.app

Exit code 0 only when both checks pass.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

# The title the current marketing build serves. A different one means the
# origin is pointed at another deployment.
EXPECTED_TITLE = "TradeLens AI — Post-Trade Journal. AI-Powered Growth."

# URL fragments that mean the visitor landed on a login wall rather than on
# the page they asked for.
_AUTH_WALL_MARKERS = (
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


def _is_auth_wall(url: str) -> bool:
    lowered = url.lower()
    return any(marker in lowered for marker in _AUTH_WALL_MARKERS)


def _title_of(html: str) -> str | None:
    lowered = html.lower()
    start = lowered.find("<title>")
    if start == -1:
        return None
    end = lowered.find("</title>", start)
    if end == -1:
        return None
    return html[start + len("<title>") : end].strip()


def _returns_to(auth_url: str, app_origin: str) -> bool:
    """True when a login wall carries a destination back to this app.

    Streamlit uses `redirect_uri`; other providers use `next` or
    `return_to`, so every query value is examined rather than one key.
    """
    app_host = (urllib.parse.urlparse(app_origin).hostname or "").lower()
    if not app_host:
        return False
    query = urllib.parse.urlparse(auth_url).query
    for _key, value in urllib.parse.parse_qsl(query):
        if app_host in urllib.parse.unquote(value).lower():
            return True
    return False


def classify_marketing(status: int, final_url: str, html: str) -> CheckResult:
    """The marketing page must be public and must be the current build."""
    if _is_auth_wall(final_url):
        return CheckResult(
            False,
            final_url,
            f"the marketing site must be publicly reachable, but it lands on "
            f"a login wall ({final_url}). Turn off deployment protection.",
        )

    if status != 200:
        return CheckResult(False, final_url, f"HTTP {status}")

    title = _title_of(html)
    normalised = (title or "").replace("&amp;", "&")
    if normalised != EXPECTED_TITLE:
        return CheckResult(
            False,
            final_url,
            f"unexpected title {title!r} — expected {EXPECTED_TITLE!r}; "
            f"the origin is serving a different build",
        )

    return CheckResult(True, final_url, "public and serving the current build")


def classify_app(status: int, final_url: str, *, app_origin: str) -> CheckResult:
    """The app may require sign-in; it may not lose the visitor.

    A redirect to a provider login is expected behaviour and passes, as
    long as it carries a destination back to this app.
    """
    if _is_auth_wall(final_url):
        if _returns_to(final_url, app_origin):
            return CheckResult(
                True,
                final_url,
                "sign-in required (expected); the redirect routes back to the app",
            )
        return CheckResult(
            False,
            final_url,
            f"sign-in redirect does not route back to {app_origin} "
            f"({final_url}); a visitor who signs in would not land on TradeLens",
        )

    if status != 200:
        return CheckResult(False, final_url, f"HTTP {status}")

    return CheckResult(True, final_url, "reachable")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Report the redirect instead of chasing it.

    The app check exists to inspect where the visitor is sent, so following
    the hop would replace the answer with whatever the login wall renders —
    and would make the check depend on a third-party host being up.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _fetch(url: str, *, follow: bool = True) -> tuple[int, str, str] | CheckResult:
    """Return (status, final_url, body), or a failing CheckResult.

    `follow` is on for the marketing page, where a hop to the canonical
    host is ordinary, and off for the app, where the hop is the finding.
    An unfollowed 3xx still names its destination in the Location header.
    """
    request = urllib.request.Request(url, headers={"User-Agent": _UA})
    opener = (
        urllib.request.build_opener()
        if follow
        else urllib.request.build_opener(_NoRedirect)
    )
    try:
        with opener.open(request, timeout=_TIMEOUT_S) as response:
            body = response.read(200_000).decode("utf-8", errors="replace")
            return response.status, response.geturl(), body
    except urllib.error.HTTPError as exc:
        location = exc.headers.get("Location") if exc.headers else None
        if 300 <= exc.code < 400 and location:
            return exc.code, location, ""
        return exc.code, exc.url or url, ""
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return CheckResult(False, url, f"request failed: {exc}")


def check_marketing(url: str) -> CheckResult:
    fetched = _fetch(url)
    if isinstance(fetched, CheckResult):
        return fetched
    return classify_marketing(*fetched)


def check_app(url: str, *, app_origin: str) -> CheckResult:
    fetched = _fetch(url, follow=False)
    if isinstance(fetched, CheckResult):
        return fetched
    status, final_url, _body = fetched
    return classify_app(status, final_url, app_origin=app_origin)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", required=True, help="public marketing origin")
    parser.add_argument("--app", required=True, help="app origin (may require sign-in)")
    args = parser.parse_args(argv)

    checks = (
        ("marketing", check_marketing(args.site)),
        ("app", check_app(args.app, app_origin=args.app)),
    )

    failed = False
    for name, result in checks:
        if result.ok:
            print(f"PASS  {name}: {result.detail or result.url}")
        else:
            failed = True
            print(f"FAIL  {name}: {result.detail}", file=sys.stderr)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
