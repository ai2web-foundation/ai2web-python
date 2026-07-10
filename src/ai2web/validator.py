"""AI2Web validation + AI Readiness scoring.

Port of @ai2web/core validateManifest (spec sections 9 & 11). MUST stay in exact
parity with the TypeScript reference and ai2web-spec/conformance/cases.json.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict
import re


class Check(TypedDict):
    ok: bool
    points: int
    label: str
    hint: Optional[str]


class ValidationResult(TypedDict):
    valid: bool
    errors: List[str]
    checks: List[Check]
    score: int
    tier: str


_VERSION_RE = re.compile(r"^\d+\.\d+(\.\d+)?$")


def _has(v: Any) -> bool:
    return v is True or (isinstance(v, dict) and v.get("enabled") is True)


def validate(m: Dict[str, Any]) -> ValidationResult:
    errors: List[str] = []
    checks: List[Check] = []
    caps = m.get("capabilities") or {}

    def cap(name: str) -> Any:
        return caps.get(name) if isinstance(caps, dict) else None

    if m.get("protocol") != "ai2w":
        errors.append("protocol must be 'ai2w'")
    if not _VERSION_RE.match(str(m.get("version", ""))):
        errors.append("version missing/invalid")
    site = m.get("site") or {}
    for k in ("name", "url", "type"):
        if not site.get(k):
            errors.append(f"site.{k} missing")
    if not isinstance(caps, dict) or not caps:
        errors.append("capabilities empty")

    actions_exist = (
        _has(cap("actions"))
        or (isinstance(m.get("actions"), list) and len(m["actions"]) > 0)
        or _has(cap("commerce"))
        or _has(cap("booking"))
    )

    score = 0

    def add(ok: bool, points: int, label: str, hint: str) -> None:
        nonlocal score
        checks.append({"ok": ok, "points": points, "label": label, "hint": None if ok else hint})
        if ok:
            score += points

    add(len(errors) == 0, 30, "Valid discovery manifest", "fix errors")
    add(_has(cap("content")), 6, "Content", "expose content module")
    add(_has(cap("commerce")) or _has(cap("booking")) or _has(cap("services")), 6,
        "Products / services / booking", "expose a commerce/services/booking module")
    add(_has(cap("search")), 4, "Search", "add a search capability")
    add(actions_exist, 5, "Actions", "declare actions")
    add(_has(cap("events")), 6, "Events / subscriptions", "publish subscribable events")
    add(bool((m.get("agent_service") or {}).get("enabled")), 4, "Agent service (A2A)", "expose /ai2w/agent")

    commerce = cap("commerce")
    add(not _has(commerce) or (isinstance(commerce, dict) and commerce.get("checkout") is True),
        4, "Checkout", "commerce present but checkout missing")

    transports = m.get("transports") or {}
    add(bool((transports.get("mcp") or {}).get("enabled") is True), 8, "MCP transport", "expose an MCP endpoint")
    add(bool((transports.get("rest") or {}).get("enabled") is True) or bool(transports.get("feeds")),
        4, "REST / feeds", "expose REST or feeds")

    auth = m.get("auth") or {}
    oauth_ok = "oauth2" in (auth.get("methods") or []) and (auth.get("oauth2") or {}).get("pkce") is True
    consent_declared = len(((m.get("consent") or {}).get("requires_user_approval_for")) or []) > 0
    add(not actions_exist or oauth_ok, 8, "OAuth2 + PKCE", "protected actions need oauth2+pkce")
    add(not actions_exist or consent_declared, 7, "Consent declared", "declare consent for sensitive actions")

    add(bool(m.get("identity")), 4, "Identity", "add identity (legal_name, policies)")
    add(bool(m.get("contact")), 4, "Contact", "add support/security contact")

    score = min(100, score)

    basic = len(errors) == 0
    standard = basic and bool(m.get("transports")) and (not actions_exist or consent_declared) and bool(m.get("contact"))
    enterprise = standard and bool(m.get("identity")) and bool(m.get("auth")) and bool(m.get("rate_limits"))
    tier = "Enterprise" if enterprise else "Standard" if standard else "Basic" if basic else "Invalid"

    return {"valid": len(errors) == 0, "errors": errors, "checks": checks, "score": score, "tier": tier}
