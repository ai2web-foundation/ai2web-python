"""Capability negotiation (spec section 5). Port of @ai2web/core negotiate()."""

from __future__ import annotations

from typing import Any, Dict, List


def _has(v: Any) -> bool:
    return v is True or (isinstance(v, dict) and v.get("enabled") is True)


def _endpoint_of(name: str, v: Any) -> str:
    if isinstance(v, dict) and isinstance(v.get("endpoint"), str):
        return v["endpoint"]
    return f"/ai2w/{name}"


def negotiate(m: Dict[str, Any], agent: Dict[str, Any] | None = None) -> Dict[str, Any]:
    agent = agent or {}
    caps = m.get("capabilities") or {}
    site_caps: List[str] = [k for k, v in caps.items() if _has(v)]

    want_caps = agent.get("capabilities")
    if want_caps is None:
        want_caps = site_caps
    capabilities = [c for c in site_caps if c in want_caps]
    unsupported = [c for c in want_caps if c not in site_caps]

    # Only transports explicitly enabled are negotiable.
    transports = m.get("transports") or {}
    site_transports = [k for k, v in transports.items() if isinstance(v, dict) and v.get("enabled") is True]
    want_transports = agent.get("transports")
    if want_transports is None:
        want_transports = site_transports
    transport = next((t for t in want_transports if t in site_transports), None)

    site_auth = (m.get("auth") or {}).get("methods") or ["none"]
    want_auth = agent.get("auth")
    if want_auth is None:
        want_auth = site_auth
    if "oauth2" in site_auth and "oauth2" in want_auth:
        auth = "oauth2"
    else:
        auth = next((a for a in want_auth if a in site_auth), None)
        if auth is None and "none" in site_auth:
            auth = "none"

    endpoints: Dict[str, str] = {c: _endpoint_of(c, caps.get(c)) for c in capabilities}
    if transport is not None and isinstance(transports.get(transport), dict) and transports[transport].get("endpoint"):
        endpoints[transport] = transports[transport]["endpoint"]

    return {
        "negotiated": {"transport": transport, "capabilities": capabilities, "auth": auth, "endpoints": endpoints},
        "unsupported": unsupported,
    }
