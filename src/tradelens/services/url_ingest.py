"""Fetch image bytes from a trader-supplied URL without becoming an SSRF hole.

A URL in a journal entry is attacker-controlled input, so this module is the
one place that decides what the server is allowed to connect to. It holds the
single public-address policy for the whole app; `ai_screenshot_service` imports
it rather than keeping a second copy that could drift.

The property this module exists for is that **the address that was validated is
the address that is connected to**. The obvious implementation — validate the
hostname, then hand the URL to `urlopen` — does not have it: the connection
performs its own, independent DNS lookup, so a hostile resolver can answer
"public" to the check and "127.0.0.1" a millisecond later to the connect. That
is DNS rebinding, and re-running the check a second time does not close it,
because the check and the connection still resolve separately.

So the host is resolved ONCE, every returned address is validated, and the
socket is opened against that exact address. The original hostname is still
what fills the `Host` header and what TLS uses for SNI and certificate
verification, so pinning the address does not weaken the connection. After the
socket is up its real peer is compared against the approved address, which is
what aborts the fetch if anything ever redirected it elsewhere.

Redirects are refused outright (a redirect is a classic pivot to an internal
host that the pre-connect check never saw), the body is capped, and the whole
exchange is time-boxed.
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
from typing import List, Optional, Tuple, Union
from urllib.parse import urlparse, urlunparse

_ALLOWED_SCHEMES = {"http", "https"}
_TIMEOUT = 5  # seconds
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB, matching storage.MAX_UPLOAD_BYTES
_USER_AGENT = "TradeLens/1.0"
_DEFAULT_PORTS = {"http": 80, "https": 443}

# One phrase for every refusal reason. Telling a caller which check they failed
# hands a prober the shape of the policy; the trader's next step is the same
# either way, so the message says what to do instead of what went wrong.
UNREACHABLE_MSG = (
    "This link could not be read as an image. "
    "Please upload the chart screenshot instead."
)
TOO_LARGE_MSG = "That image is too large to read from a link (max 10 MB)."


class UrlIngestError(ValueError):
    """A URL that will not be fetched, carrying a message a trader can act on."""


_IPAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]


def _is_public_address(ip: _IPAddress) -> bool:
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_unspecified
        or ip.is_multicast
    )


def _resolve_public_addresses(hostname: str, port: Optional[int]) -> List[Tuple]:
    """Every address `hostname` resolves to, or [] if ANY of them is not public.

    All-or-nothing on purpose: a host that answers with one public and one
    private address is a rebinding attempt with the timing removed, and picking
    the public one would connect exactly where the attacker wanted on the next
    lookup.
    """
    try:
        infos = socket.getaddrinfo(hostname, port or None)
    except (socket.gaierror, UnicodeError, ValueError, OSError):
        return []
    if not infos:
        return []
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return []
        if not _is_public_address(ip):
            return []
    return list(infos)


def is_public_url(url: str) -> bool:
    """True only when `url` is http(s) and its host resolves entirely to public
    IPs. Rejects loopback / private / link-local / reserved / multicast targets.

    A pre-flight answer only. It cannot make a later connection safe — that is
    what `fetch_image_bytes` pinning the resolved address is for.
    """
    parsed = urlparse(url) if isinstance(url, str) else None
    if parsed is None or parsed.scheme not in _ALLOWED_SCHEMES or not parsed.hostname:
        return False
    try:
        port = parsed.port
    except ValueError:
        return False
    return bool(_resolve_public_addresses(parsed.hostname, port))


def _request_target(parsed) -> str:
    return urlunparse(("", "", parsed.path or "/", parsed.params, parsed.query, ""))


def _open_pinned(scheme: str, hostname: str, port: int, sockaddr: Tuple):
    """A connection to `sockaddr` that still speaks as `hostname`.

    `_create_connection` is replaced rather than the host, so `Host:` and the
    TLS `server_hostname` both remain the name the trader typed — pinning the
    address must not turn into disabling certificate verification.
    """
    approved_ip = sockaddr[0]
    if scheme == "https":
        conn = http.client.HTTPSConnection(
            hostname, port, timeout=_TIMEOUT, context=ssl.create_default_context()
        )
    else:
        conn = http.client.HTTPConnection(hostname, port, timeout=_TIMEOUT)

    def _connect_to_validated(address, timeout=None, source_address=None):
        return socket.create_connection((approved_ip, sockaddr[1]), _TIMEOUT)

    conn._create_connection = _connect_to_validated
    # Anything the socket/TLS layer can raise here — refused connection, a
    # timeout, a bad certificate — is a network fact about an attacker-chosen
    # host. It must come out as the same generic UrlIngestError as a policy
    # refusal, or the exception type itself becomes an oracle that tells a
    # prober "connect failed" apart from "policy refused" on public addresses.
    try:
        conn.connect()
    except (OSError, ssl.SSLError) as exc:
        conn.close()
        raise UrlIngestError(UNREACHABLE_MSG) from exc

    # The socket's real peer, not the name we asked for. If anything at all put
    # this connection somewhere other than the address that passed the policy,
    # the fetch stops here rather than reading a byte from it.
    try:
        peer = conn.sock.getpeername()[0]
        peer_ip = ipaddress.ip_address(peer)
    except (OSError, ValueError) as exc:
        # ValueError covers a peer string ipaddress can't parse (e.g. a
        # zone-suffixed IPv6 literal like "fe80::1%eth0") — a parse failure is
        # not proof of safety, so it must refuse rather than propagate raw.
        conn.close()
        raise UrlIngestError(UNREACHABLE_MSG) from exc
    # Compare as address objects, not strings: two strings can denote the same
    # address under a resolver that doesn't share CPython's normalization, and
    # this comparison is a security boundary, not a display concern.
    if peer_ip != ipaddress.ip_address(approved_ip) or not _is_public_address(peer_ip):
        conn.close()
        raise UrlIngestError(UNREACHABLE_MSG)
    return conn


def _open_for(url: str):
    """Parse, resolve once, validate, and return a connection pinned to the
    address that passed. Every network request in this module starts here, so
    there is no second way to reach the socket layer with a weaker check."""
    if not isinstance(url, str):
        raise UrlIngestError(UNREACHABLE_MSG)
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.hostname:
        raise UrlIngestError(UNREACHABLE_MSG)
    try:
        port = parsed.port or _DEFAULT_PORTS[parsed.scheme]
    except ValueError as exc:
        raise UrlIngestError(UNREACHABLE_MSG) from exc

    infos = _resolve_public_addresses(parsed.hostname, parsed.port)
    if not infos:
        raise UrlIngestError(UNREACHABLE_MSG)

    conn = _open_pinned(parsed.scheme, parsed.hostname, port, (infos[0][4][0], port))
    return conn, parsed


def probe_content_type(url: str) -> Optional[str]:
    """The lowercased `Content-Type` a HEAD reports, or None.

    A probe is still a request the server makes on a trader's say-so, so it
    goes through the same pinned connection as the download rather than an
    opener that would resolve the name again.
    """
    try:
        conn, parsed = _open_for(url)
    except UrlIngestError:
        return None
    try:
        conn.request(
            "HEAD", _request_target(parsed), headers={"User-Agent": _USER_AGENT}
        )
        response = conn.getresponse()
        if response.status != 200:
            return None
        return (response.headers.get("Content-Type") or "").lower()
    except (OSError, http.client.HTTPException):
        return None
    finally:
        conn.close()


def fetch_image_bytes(url: str) -> bytes:
    """The bytes at `url`, or raise `UrlIngestError`.

    The bytes are NOT trusted and NOT an image yet — the caller must still put
    them through the quarantine/`validate_and_normalise` path that every
    browser upload goes through. This function's only job is to make the
    network request safe to have made.
    """
    conn, parsed = _open_for(url)
    try:
        conn.request(
            "GET",
            _request_target(parsed),
            headers={"User-Agent": _USER_AGENT, "Accept": "image/*"},
        )
        response = conn.getresponse()
        # A redirect is not followed and not even read: following one would
        # connect to a host this policy never examined.
        if response.status != 200:
            raise UrlIngestError(UNREACHABLE_MSG)
        data = response.read(_MAX_BYTES + 1)
    except UrlIngestError:
        raise
    except (OSError, http.client.HTTPException) as exc:
        raise UrlIngestError(UNREACHABLE_MSG) from exc
    finally:
        conn.close()

    if len(data) > _MAX_BYTES:
        raise UrlIngestError(TOO_LARGE_MSG)
    if not data:
        raise UrlIngestError(UNREACHABLE_MSG)
    return data
