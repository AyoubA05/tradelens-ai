"""The URL fetcher's SSRF policy, tested as behaviour rather than as helpers.

The guard that matters here is DNS rebinding, and it is the easiest one to
"test" without testing: asserting that `is_public_url` returns False proves
nothing about the connection, because the connection resolves the name again on
its own. Every test below drives `fetch_image_bytes` and asserts what the
socket layer was asked to do.
"""

from __future__ import annotations

import io
import socket
import ssl

import pytest

from src.tradelens.services import url_ingest
from src.tradelens.services.url_ingest import UrlIngestError, fetch_image_bytes

PUBLIC_IP = "93.184.216.34"


def _addrinfo(ip, port=0):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]


def _response(status=200, body=b"\x89PNG\r\n\x1a\nfake", headers=b""):
    return b"HTTP/1.1 %d OK\r\nContent-Length: %d\r\n%s\r\n%s" % (
        status,
        len(body),
        headers,
        body,
    )


class _FakeSocket:
    """Enough socket for http.client, and a peer address a test can choose."""

    def __init__(self, response: bytes, peer_ip: str, peer_port: int = 80):
        self._rfile = io.BytesIO(response)
        self._peer = (peer_ip, peer_port)
        self.sent = b""
        self.closed = False

    def sendall(self, data):
        self.sent += bytes(data)

    def makefile(self, mode="rb", bufsize=-1):
        return self._rfile

    def getpeername(self):
        return self._peer

    def setsockopt(self, *args):
        pass

    def settimeout(self, *args):
        pass

    def close(self):
        self.closed = True


def _wire(monkeypatch, *, resolves_to, connects_to=None, response=None, port=80):
    """Resolve to one address and hand back a socket whose peer is another.

    `connects_to` defaults to `resolves_to`, i.e. an honest host. Passing a
    different value is exactly the rebinding scenario: the policy sees a public
    address and the socket lands somewhere else.
    """
    calls = []
    sock = _FakeSocket(
        response if response is not None else _response(),
        connects_to or resolves_to,
        port,
    )
    monkeypatch.setattr(
        url_ingest.socket, "getaddrinfo", lambda host, p=None: _addrinfo(resolves_to, p)
    )

    def _create_connection(address, timeout=None, source_address=None):
        calls.append(address)
        return sock

    monkeypatch.setattr(url_ingest.socket, "create_connection", _create_connection)
    return calls, sock


# ------------------------------------------------------------- address policy


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",  # loopback
        "10.0.0.5",  # private
        "169.254.169.254",  # link-local: the cloud metadata endpoint
        "240.0.0.1",  # reserved
        "224.0.0.1",  # multicast
        "0.0.0.0",  # unspecified
    ],
)
def test_a_non_public_address_is_never_connected_to(monkeypatch, ip):
    calls, _ = _wire(monkeypatch, resolves_to=ip)

    with pytest.raises(UrlIngestError):
        fetch_image_bytes("http://chart.example/x.png")

    assert calls == [], "a refused host must not reach the socket layer at all"


@pytest.mark.parametrize(
    "url",
    ["file:///etc/passwd", "ftp://example.com/x.png", "gopher://example.com/", "//x"],
)
def test_a_non_http_scheme_is_refused(monkeypatch, url):
    calls, _ = _wire(monkeypatch, resolves_to=PUBLIC_IP)

    with pytest.raises(UrlIngestError):
        fetch_image_bytes(url)

    assert calls == []


def test_a_host_that_resolves_to_a_mix_of_public_and_private_is_refused(monkeypatch):
    """One private answer poisons the whole set: choosing the public one would
    connect wherever the attacker wanted on the next lookup."""
    monkeypatch.setattr(
        url_ingest.socket,
        "getaddrinfo",
        lambda host, p=None: _addrinfo(PUBLIC_IP, p) + _addrinfo("127.0.0.1", p),
    )
    calls = []
    monkeypatch.setattr(
        url_ingest.socket,
        "create_connection",
        lambda *a, **k: calls.append(a) or _FakeSocket(_response(), PUBLIC_IP),
    )

    with pytest.raises(UrlIngestError):
        fetch_image_bytes("http://chart.example/x.png")

    assert calls == []


# ------------------------------------------------------------- rebinding


def test_a_host_that_resolves_private_at_connect_time_aborts_the_fetch(monkeypatch):
    """THE rebinding test.

    The name passes the policy — it resolves to a public address — and then the
    socket lands on loopback, which is what a hostile resolver answering twice
    achieves. The fetch must abort. Asserting `is_public_url` returned True
    here would be asserting the bug.
    """
    calls, sock = _wire(monkeypatch, resolves_to=PUBLIC_IP, connects_to="127.0.0.1")
    assert url_ingest.is_public_url("http://rebind.example/x.png") is True

    with pytest.raises(UrlIngestError):
        fetch_image_bytes("http://rebind.example/x.png")

    assert sock.sent == b"", "not one request byte may go to the rebound address"
    assert sock.closed is True


def test_the_connection_is_made_to_the_validated_address_not_the_hostname(monkeypatch):
    """Pinning is the fix; connecting by name would let DNS answer twice.

    If the implementation handed the hostname to the socket layer — the shape
    a second `is_public_url` call leaves in place — this records the name and
    fails.
    """
    calls, sock = _wire(monkeypatch, resolves_to=PUBLIC_IP)

    fetch_image_bytes("http://chart.example/x.png")

    assert calls == [(PUBLIC_IP, 80)]


def test_the_host_header_stays_the_original_hostname(monkeypatch):
    """Pinning the address must not change who we claim to be talking to."""
    _, sock = _wire(monkeypatch, resolves_to=PUBLIC_IP)

    fetch_image_bytes("http://chart.example/x.png")

    assert b"Host: chart.example\r\n" in sock.sent
    assert PUBLIC_IP.encode() not in sock.sent


def test_tls_verifies_against_the_hostname_not_the_pinned_address(monkeypatch):
    """Certificate verification must still be against the name, or pinning the
    address would have quietly traded one hole for a worse one."""
    seen = {}
    sock = _FakeSocket(_response(), PUBLIC_IP, 443)

    class _Context:
        # http.client inspects these before it will wrap anything.
        verify_mode = ssl.CERT_REQUIRED
        check_hostname = True

        def wrap_socket(self, raw, server_hostname=None, **kwargs):
            seen["server_hostname"] = server_hostname
            return raw

    monkeypatch.setattr(url_ingest.ssl, "create_default_context", lambda: _Context())
    monkeypatch.setattr(
        url_ingest.socket, "getaddrinfo", lambda host, p=None: _addrinfo(PUBLIC_IP, p)
    )
    monkeypatch.setattr(url_ingest.socket, "create_connection", lambda *a, **k: sock)

    fetch_image_bytes("https://chart.example/x.png")

    assert seen["server_hostname"] == "chart.example"


# ------------------------------------------------------------- transfer rules


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_a_redirect_is_refused_rather_than_followed(monkeypatch, status):
    """A redirect is a pivot to a host the address policy never examined."""
    # A body on the redirect on purpose: a handler that merely reads whatever
    # comes back would return these bytes, so the test fails unless the STATUS
    # itself is what refuses the response.
    decoy = b"\x89PNG\r\n\x1a\nredirect-body"
    redirect = (
        b"HTTP/1.1 %d Moved\r\nLocation: http://169.254.169.254/latest\r\nContent-Length: %d\r\n\r\n%s"
        % (
            status,
            len(decoy),
            decoy,
        )
    )
    _, sock = _wire(monkeypatch, resolves_to=PUBLIC_IP, response=redirect)

    with pytest.raises(UrlIngestError):
        fetch_image_bytes("http://chart.example/x.png")

    assert sock.sent.count(b"GET ") == 1, "the redirect target is never requested"


def test_a_body_over_the_cap_is_refused(monkeypatch):
    oversized = b"\x89PNG\r\n\x1a\n" + b"x" * url_ingest._MAX_BYTES
    _, _sock = _wire(
        monkeypatch, resolves_to=PUBLIC_IP, response=_response(body=oversized)
    )

    with pytest.raises(UrlIngestError) as exc:
        fetch_image_bytes("http://chart.example/x.png")

    assert "too large" in str(exc.value)


def test_a_non_200_is_refused(monkeypatch):
    _, _sock = _wire(
        monkeypatch, resolves_to=PUBLIC_IP, response=_response(status=404, body=b"")
    )

    with pytest.raises(UrlIngestError):
        fetch_image_bytes("http://chart.example/x.png")


def test_a_public_host_returns_its_bytes_unchanged(monkeypatch):
    payload = b"\x89PNG\r\n\x1a\nchart-bytes"
    _wire(monkeypatch, resolves_to=PUBLIC_IP, response=_response(body=payload))

    assert fetch_image_bytes("http://chart.example/x.png") == payload
