"""Export adapters (RFC-0015): project the one canonical AI2Web manifest into other wire
formats and discovery surfaces. Port of @ai2web/core export.ts.

Each export is a best-effort projection; where a target cannot represent a field, it is omitted
rather than misstated. The canonical /ai2w manifest stays authoritative for execution.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


def _enabled(v: Any) -> bool:
    return v is True or (isinstance(v, dict) and v.get("enabled") is True)


def _trim_url(u: str) -> str:
    return u.rstrip("/")


def _enabled_capabilities(m: Dict[str, Any]) -> List[str]:
    caps = m.get("capabilities") or {}
    return [k for k, v in caps.items() if _enabled(v)]


def to_llms_txt(m: Dict[str, Any]) -> str:
    """Project the manifest to an ``llms.txt`` document: a plain-text summary and set of links a
    model can read for content and guidance. Reads only; no actions are exposed here."""
    site = m.get("site") or {}
    base = _trim_url(site.get("url", ""))
    lines: List[str] = [f"# {site.get('name', '')}"]
    if site.get("description"):
        lines += ["", f"> {site['description']}"]

    caps = _enabled_capabilities(m)
    if caps:
        lines += ["", "## Capabilities", *[f"- {c}" for c in caps]]

    knowledge = m.get("knowledge") or []
    if knowledge:
        lines.append("")
        lines.append("## Knowledge")
        for k in knowledge:
            ref = k.get("ref", "")
            if not ref.startswith("http"):
                ref = base + ("" if ref.startswith("/") else "/") + ref
            lines.append(f"- [{k.get('name') or k.get('id')}]({ref})")

    actions = m.get("actions") or []
    if actions:
        lines.append("")
        lines.append("## Actions")
        for a in actions:
            lines.append(f"- {a.get('name')}: {a.get('description')}")

    lines += ["", "## Discovery", f"- Manifest: {base}/ai2w"]
    return "\n".join(lines) + "\n"


def to_agent_json(m: Dict[str, Any]) -> Dict[str, Any]:
    """Project the manifest to a generic ``agent.json`` style capability document. Best-effort,
    format-neutral projection of identity, capabilities, actions (with bindings), knowledge and
    policies. Consent/governance a target cannot express are carried as a ``policies`` object
    rather than dropped silently."""
    site = m.get("site") or {}
    actions = m.get("actions") or []
    consent = m.get("consent") or {}
    return {
        "schema": "agent-capabilities",
        "name": site.get("name"),
        "description": site.get("description"),
        "url": site.get("url"),
        "identity": m.get("identity"),
        "capabilities": _enabled_capabilities(m),
        "actions": [
            {
                "name": a.get("name"),
                "intent": a.get("intent"),
                "description": a.get("description"),
                "risk": a.get("risk"),
                "requires_consent": a.get("requires_user_approval"),
                "requires_auth": a.get("requires_auth"),
                "input_schema": a.get("input_schema"),
                "bindings": a.get("bindings") or [{"kind": "rest", "ref": a.get("endpoint")}],
            }
            for a in actions
        ],
        "knowledge": m.get("knowledge"),
        "transports": m.get("transports"),
        "policies": {
            "consent": consent.get("requires_user_approval_for"),
            "governance": m.get("governance"),
            "usage": m.get("usage_policy"),
            "legal": m.get("legal"),
        },
    }


def to_oauth_protected_resource(m: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """OAuth 2.0 Protected Resource metadata (RFC 9728), for
    ``/.well-known/oauth-protected-resource``. MCP clients read this to discover which
    authorization server guards the resource before starting a flow.

    Returns ``None`` when the site does not advertise oauth2, so an auth surface the site
    cannot honour is never published.
    """
    auth = m.get("auth") or {}
    if "oauth2" not in (auth.get("methods") or []):
        return None
    base = _trim_url(str((m.get("site") or {}).get("url", "")))
    oauth2 = auth.get("oauth2") or {}
    issuer = base
    authz = oauth2.get("authorization_url")
    if authz:
        parts = urlparse(str(authz))
        if parts.scheme and parts.netloc:
            issuer = f"{parts.scheme}://{parts.netloc}"
    doc: Dict[str, Any] = {
        "resource": f"{base}/ai2w",
        "authorization_servers": [issuer],
        "bearer_methods_supported": ["header"],
    }
    scopes = oauth2.get("scopes")
    if scopes:
        doc["scopes_supported"] = list(scopes)
    return doc


def to_content_signals(m: Dict[str, Any]) -> Optional[str]:
    """Map ``usage_policy`` onto Content Signals tokens.

    ``search`` stays ``yes`` because AI2Web exists to be discoverable; the AI signals are only
    asserted when the manifest states them, so an unset policy is never reported as a refusal.
    Returns ``None`` when no policy is declared.
    """
    p = m.get("usage_policy")
    if not isinstance(p, dict) or not p:
        return None
    signals = ["search=yes"]
    if isinstance(p.get("content_reproduction"), bool):
        signals.append("ai-input=" + ("yes" if p["content_reproduction"] else "no"))
    if isinstance(p.get("model_training"), bool):
        signals.append("ai-train=" + ("yes" if p["model_training"] else "no"))
    return ", ".join(signals)


def to_robots_txt(m: Dict[str, Any]) -> str:
    """A robots.txt FRAGMENT carrying the usage policy and a pointer to the manifest.

    Append it to an existing robots.txt; it is never a replacement, and emits no Disallow rules.
    """
    base = _trim_url(str((m.get("site") or {}).get("url", "")))
    signals = to_content_signals(m)
    lines = [f"# AI2Web usage policy, projected from {base}/ai2w", "User-agent: *"]
    if signals is not None:
        lines.append(f"Content-Signal: {signals}")
    if (m.get("usage_policy") or {}).get("bulk_extraction") is False:
        lines.append("# bulk_extraction: false - please use the /ai2w endpoints instead of crawling")
    lines.append(f"# AI2Web-Manifest: {base}/ai2w")
    return "\n".join(lines) + "\n"


def to_discovery_link_header(m: Dict[str, Any]) -> str:
    """Value for an HTTP ``Link`` header advertising the manifest to non-HTML clients."""
    base = _trim_url(str((m.get("site") or {}).get("url", "")))
    return f'<{base}/ai2w>; rel="ai2w"'
