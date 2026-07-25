"""The anonymous landing-to-app journey.

Two failures shipped at once and neither was visible from the repo: the
canonical domain served an older, differently-positioned site, and the app
URL bounced anonymous visitors into Streamlit's own provider login instead
of TradeLens's auth screen. Both are deployment-side, so only a check
against the live hosts can catch them.

classify() is pure so the rules are testable without network access.
"""

import http.server
import threading
from contextlib import contextmanager

from scripts.verify_public_funnel import EXPECTED_TITLE, check_endpoint, classify


# --- marketing page rules --------------------------------------------------


def test_public_marketing_page_passes():
    result = classify(
        200, "https://tradelens-ai.com/", f"<title>{EXPECTED_TITLE}</title>"
    )
    assert result.ok


def test_wrong_marketing_version_fails():
    """The exact symptom: the domain serving a different build."""
    html = (
        "<title>TradeLens AI — Behavioral Trading Analytics &amp; AI Coaching</title>"
    )
    result = classify(200, "https://tradelens-ai.com/", html)
    assert not result.ok
    assert "unexpected title" in result.detail


def test_missing_title_fails():
    result = classify(200, "https://tradelens-ai.com/", "<h1>hello</h1>")
    assert not result.ok
    assert "unexpected title" in result.detail


def test_non_200_fails():
    result = classify(404, "https://tradelens-ai.com/", "")
    assert not result.ok
    assert "404" in result.detail


# --- provider-auth rules ---------------------------------------------------


def test_provider_auth_redirect_fails():
    result = classify(303, "https://share.streamlit.io/-/auth/app", "")
    assert not result.ok
    assert "provider authentication" in result.detail


def test_sso_api_landing_fails():
    result = classify(200, "https://vercel.com/sso-api?url=x", "")
    assert not result.ok
    assert "provider authentication" in result.detail


def test_login_path_landing_fails():
    result = classify(200, "https://example.com/-/login", "")
    assert not result.ok
    assert "provider authentication" in result.detail


def test_app_endpoint_does_not_require_a_marketing_title():
    """The app is a different product surface; only the auth check applies."""
    result = classify(
        200,
        "https://tradelens-app.streamlit.app/",
        "<title>App</title>",
        expect_title=False,
    )
    assert result.ok


# --- live check against a local server -------------------------------------


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


def test_check_endpoint_passes_against_a_correct_server():
    with _serve(_html_handler(f"<title>{EXPECTED_TITLE}</title>")) as url:
        assert check_endpoint(url).ok


def test_check_endpoint_reports_a_wrong_build():
    with _serve(_html_handler("<title>Something Else</title>")) as url:
        result = check_endpoint(url)
        assert not result.ok
        assert "unexpected title" in result.detail


def test_check_endpoint_reports_network_failure_clearly():
    # Nothing is listening on this port.
    result = check_endpoint("http://127.0.0.1:9/")
    assert not result.ok
    assert result.detail


def test_unfollowed_redirect_is_judged_by_its_destination():
    """urllib surfaces a cross-host 303 as an error instead of following it.

    The Location header still names the destination, so a provider login
    wall must be reported as such rather than as a bare 'HTTP 303'.
    """

    class Redirector(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 — stdlib naming
            self.send_response(303)
            self.send_header(
                "Location", "https://share.streamlit.io/-/auth/app?redirect_uri=x"
            )
            self.end_headers()

        def log_message(self, *args):
            pass

    with _serve(Redirector) as url:
        result = check_endpoint(url, expect_title=False)
        assert not result.ok
        assert "provider authentication" in result.detail
