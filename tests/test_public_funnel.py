"""The anonymous landing-to-app journey.

The two endpoints have different contracts, so they get different checks.

The marketing site must be *public*: an anonymous visitor has to see the
current build, with no login wall in front of it. That failure shipped
once — the canonical domain silently served an older, differently
positioned build — and only a check against the live host catches it.

The app is deliberately gated. A sign-in wall there is correct behaviour,
not a fault. What still has to hold is that the gate *routes back*: the
redirect must carry the visitor to a login for this app, so signing in
returns them to TradeLens. A redirect that drops the destination, or a
host that is simply down, is a real failure and must still be reported.
"""

import http.server
import threading
from contextlib import contextmanager

from scripts.verify_public_funnel import (
    EXPECTED_TITLE,
    check_app,
    check_marketing,
    classify_app,
    classify_marketing,
)

APP = "https://tradelens-app.streamlit.app"
STREAMLIT_AUTH = (
    "https://share.streamlit.io/-/auth/app"
    "?redirect_uri=https%3A%2F%2Ftradelens-app.streamlit.app%2F"
)


# --- marketing: must be public and must be the current build ---------------


def test_public_marketing_page_passes():
    result = classify_marketing(
        200, "https://www.tradelensai.io/", f"<title>{EXPECTED_TITLE}</title>"
    )
    assert result.ok


def test_wrong_marketing_version_fails():
    """The exact symptom: the domain serving a different build."""
    html = (
        "<title>TradeLens AI — Behavioral Trading Analytics &amp; AI Coaching</title>"
    )
    result = classify_marketing(200, "https://www.tradelensai.io/", html)
    assert not result.ok
    assert "unexpected title" in result.detail


def test_missing_title_fails():
    result = classify_marketing(200, "https://www.tradelensai.io/", "<h1>hello</h1>")
    assert not result.ok
    assert "unexpected title" in result.detail


def test_non_200_marketing_fails():
    result = classify_marketing(404, "https://www.tradelensai.io/", "")
    assert not result.ok
    assert "404" in result.detail


def test_marketing_behind_a_login_wall_fails():
    """Deployment protection on the marketing site hides it from everyone."""
    result = classify_marketing(200, "https://vercel.com/sso-api?url=x", "")
    assert not result.ok
    assert "must be publicly reachable" in result.detail


# --- app: a sign-in wall is expected, losing the destination is not --------


def test_app_sign_in_redirect_is_expected_behaviour():
    """The app is gated on purpose; this is a pass, not a failure."""
    result = classify_app(303, STREAMLIT_AUTH, app_origin=APP)
    assert result.ok
    assert "sign-in" in result.detail


def test_app_reachable_without_a_redirect_also_passes():
    """If the app serves its own auth screen directly, that is fine too."""
    result = classify_app(200, APP + "/", app_origin=APP)
    assert result.ok


def test_auth_redirect_that_loses_the_destination_fails():
    """A login wall that won't return the visitor is a broken funnel."""
    result = classify_app(303, "https://share.streamlit.io/-/auth/app", app_origin=APP)
    assert not result.ok
    assert "does not route back" in result.detail


def test_auth_redirect_to_a_different_app_fails():
    result = classify_app(
        303,
        "https://share.streamlit.io/-/auth/app?redirect_uri=https%3A%2F%2Fsomeone-else.streamlit.app%2F",
        app_origin=APP,
    )
    assert not result.ok
    assert "does not route back" in result.detail


def test_app_server_error_still_fails():
    result = classify_app(500, APP + "/", app_origin=APP)
    assert not result.ok
    assert "500" in result.detail


def test_app_not_found_still_fails():
    result = classify_app(404, APP + "/", app_origin=APP)
    assert not result.ok


# --- live checks against a local server ------------------------------------


@contextmanager
def _serve(handler_cls):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        server.server_close()


def _html_handler(body: str, status: int = 200):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 — stdlib naming
            payload = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):  # keep test output quiet
            pass

    return Handler


def _redirect_handler(location: str):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 — stdlib naming
            self.send_response(303)
            self.send_header("Location", location)
            self.end_headers()

        def log_message(self, *args):
            pass

    return Handler


def test_check_marketing_passes_against_a_correct_server():
    with _serve(_html_handler(f"<title>{EXPECTED_TITLE}</title>")) as url:
        assert check_marketing(url).ok


def test_check_marketing_reports_a_wrong_build():
    with _serve(_html_handler("<title>Something Else</title>")) as url:
        result = check_marketing(url)
        assert not result.ok
        assert "unexpected title" in result.detail


def test_check_marketing_reports_network_failure_clearly():
    result = check_marketing("http://127.0.0.1:9/")
    assert not result.ok
    assert result.detail


def test_check_app_accepts_a_returning_sign_in_redirect():
    """urllib surfaces a cross-host 303 as an error rather than following it;
    the Location header still names the destination."""
    with _serve(_redirect_handler(STREAMLIT_AUTH)) as url:
        result = check_app(url, app_origin=APP)
        assert result.ok


def test_check_app_rejects_a_redirect_that_drops_the_destination():
    with _serve(_redirect_handler("https://share.streamlit.io/-/auth/app")) as url:
        result = check_app(url, app_origin=APP)
        assert not result.ok
        assert "does not route back" in result.detail


def test_check_app_reports_an_unreachable_host():
    result = check_app("http://127.0.0.1:9/", app_origin=APP)
    assert not result.ok
    assert result.detail
