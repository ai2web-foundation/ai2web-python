"""Framework-agnostic AI2Web request handler. Port of @ai2web/server.

Returns a dict {status, headers, body}; adapt to Flask/FastAPI/Django/etc.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional
import re

from .negotiator import negotiate
from .schema import validate_schema

_CORS = {
    "access-control-allow-origin": "*",
    "access-control-allow-methods": "GET, POST, OPTIONS",
    "access-control-allow-headers": "content-type, authorization",
}

_ACTION_RE = re.compile(r"^/ai2w/actions/([a-z0-9_-]+)$", re.IGNORECASE)
_MODULE_RE = re.compile(r"^/ai2w/([a-z0-9_-]+)$", re.IGNORECASE)


def _json(status: int, body: Any) -> Dict[str, Any]:
    return {"status": status, "headers": {"content-type": "application/json; charset=utf-8", **_CORS}, "body": body}


def _error(status: int, code: str, message: str, retryable: bool = False) -> Dict[str, Any]:
    return _json(status, {"error": {"code": code, "message": message, "retryable": retryable}})


def handle(
    opts: Dict[str, Any],
    method: str,
    path: str,
    body: Any = None,
    origin: Optional[str] = None,
) -> Dict[str, Any]:
    manifest = opts["manifest"]
    modules: Dict[str, Callable] = opts.get("modules") or {}
    actions: Dict[str, Callable] = opts.get("actions") or {}
    validate_input = opts.get("validate_input", True)
    declared_actions = {a.get("name"): a for a in (manifest.get("actions") or [])}

    path = ("/" + path.strip("/")) if path.strip("/") else "/"
    method = method.upper()

    if method == "OPTIONS":
        return {"status": 204, "headers": dict(_CORS), "body": None}

    if path == "/.well-known/ai2w":
        if origin:
            return _json(200, {"ai2w": origin.rstrip("/") + "/ai2w"})
        return _json(200, manifest)

    if path in ("/ai2w", "/ai", "/.ai"):
        if method != "GET":
            return _error(405, "invalid_request", "Use GET for the manifest.")
        return _json(200, manifest)

    if path == "/ai2w/negotiate":
        b = body if isinstance(body, dict) else {}
        supports = (b.get("agent") or {}).get("supports") or b.get("supports") or b
        return _json(200, negotiate(manifest, supports if isinstance(supports, dict) else {}))

    m = _ACTION_RE.match(path)
    if m:
        name = m.group(1).replace("-", "_")
        fn = actions.get(name)
        if not fn:
            return _error(404, "unsupported_capability", f"Unknown action '{name}'.")
        declared = declared_actions.get(name)
        if validate_input and declared and declared.get("input_schema"):
            result = validate_schema(body if body is not None else {}, declared["input_schema"])
            if not result.valid:
                return _error(400, "invalid_request", "Request does not match the declared input schema: " + "; ".join(result.errors) + ".")
        return _json(200, fn(body))

    m = _MODULE_RE.match(path)
    if m:
        name = m.group(1)
        fn = modules.get(name)
        if not fn:
            return _error(404, "unsupported_capability", f"Module '{name}' not exposed.")
        return _json(200, fn(body))

    return _error(404, "invalid_request", f"No AI2Web route for {path}.")
