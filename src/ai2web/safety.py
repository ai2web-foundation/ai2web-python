"""SSRF guard. Parity with @ai2web/core safety.ts.

Blocks the obvious pivots (loopback, private ranges, cloud metadata, link-local,
non-http schemes). Literal host/IP check - not by itself DNS-rebind safe.
"""

from __future__ import annotations

from urllib.parse import urlparse
import re

_IPV4_RE = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$")


def is_safe_public_url(raw: str) -> bool:
    try:
        u = urlparse(raw)
    except Exception:
        return False
    if u.scheme not in ("https", "http"):
        return False
    host = (u.hostname or "").lower()
    if not host:
        return False
    if host == "localhost" or host.endswith(".localhost"):
        return False
    # Only treat fc/fd/fe80 as IPv6 ULA/link-local when the host is an IPv6 literal
    # (guard on ":"), so real domains like "fcbarcelona.com" are not blocked.
    if ":" in host and (host == "::1" or host.startswith("fc") or host.startswith("fd") or host.startswith("fe80")):
        return False
    m = _IPV4_RE.match(host)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if a in (0, 10, 127):
            return False
        if a == 169 and b == 254:  # link-local + cloud metadata
            return False
        if a == 172 and 16 <= b <= 31:
            return False
        if a == 192 and b == 168:
            return False
        if a == 100 and 64 <= b <= 127:  # CGNAT
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
