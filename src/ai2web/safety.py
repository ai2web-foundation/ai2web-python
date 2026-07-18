"""SSRF guard. Parity with @ai2web/core safety.

Blocks the obvious pivots (loopback, private ranges, cloud metadata, link-local,
non-http schemes) AND the alternative IP encodings that HTTP clients resolve to
those same addresses (decimal / hex / octal / short-form IPv4, and IPv4-mapped
IPv6). Literal host/IP check - not by itself DNS-rebind safe.
"""

from __future__ import annotations

from urllib.parse import urlparse
import re

_IPV4_RE = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$")
_IPV4_TAIL = re.compile(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})$")


def _ipv4_blocked(host: str) -> bool:
    """True if a standard dotted-quad is loopback/private/reserved (or has an invalid octet)."""
    m = _IPV4_RE.match(host)
    if not m:
        return False
    parts = [int(x) for x in m.groups()]
    if any(p > 255 for p in parts):
        return True  # not a real address; refuse
    a, b = parts[0], parts[1]
    if a in (0, 10, 127):
        return True
    if a == 169 and b == 254:  # link-local + cloud metadata (169.254.169.254)
        return True
    if a == 172 and 16 <= b <= 31:
        return True
    if a == 192 and b == 168:
        return True
    if a == 100 and 64 <= b <= 127:  # CGNAT
        return True
    return False


def is_safe_public_url(raw: str) -> bool:
    try:
        u = urlparse(raw)
    except Exception:
        return False
    if u.scheme not in ("https", "http"):
        return False
    host = (u.hostname or "").lower()
    if not host or host == "localhost" or host.endswith(".localhost"):
        return False

    # IPv6 literal (urlparse strips the [] brackets).
    if ":" in host:
        # IPv4-mapped / compat (::ffff:a.b.c.d, ::a.b.c.d): range-check the embedded IPv4.
        m = _IPV4_TAIL.search(host)
        if m and _ipv4_blocked(m.group(1)):
            return False
        if host == "::1" or host.startswith(("fc", "fd", "fe80")):
            return False
        return True

    # Hex-encoded IP (0x7f000001, or a dotted octet like 0x7f): a client resolves these to an IP.
    if re.search(r"(^|\.)0x", host):
        return False

    # Standard dotted-quad IPv4.
    if _IPV4_RE.match(host):
        return not _ipv4_blocked(host)

    # Any remaining all-numeric host is an alternative IPv4 encoding (decimal integer, octal,
    # or short form like 127.1) that a client resolves to an IP. No real domain looks like this.
    if not re.search(r"[a-z]", host):
        return False

    return True


def assert_safe_public_url(raw: str) -> str:
    if not is_safe_public_url(raw):
        raise ValueError(f"ai2w: refusing to fetch non-public or unsafe URL: {raw}")
    return raw


def same_origin(a: str, b: str) -> bool:
    try:
        pa, pb = urlparse(a), urlparse(b)
        return (pa.scheme, pa.hostname, pa.port) == (pb.scheme, pb.hostname, pb.port)
    except Exception:
        return False
