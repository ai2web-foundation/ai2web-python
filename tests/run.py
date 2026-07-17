"""AI2Web Python SDK tests. Dependency-free - run with `python tests/run.py`.

Includes the shared conformance contract (conformance_cases.json, a copy of the
spec's cases.json) to prove Python parity with the TS/PHP reference validators.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ai2web import (  # noqa: E402
    ai2web, validate, negotiate, handle, is_safe_public_url, validate_schema,
    to_llms_txt, to_agent_json,
)

failures = 0


def check(cond, label, detail=None):
    global failures
    print(("PASS" if cond else "FAIL") + "  " + label)
    if not cond:
        failures += 1
        if detail is not None:
            print("      got:", json.dumps(detail, default=str))


# --- builder + validate ---
m = (
    ai2web({"name": "Example Store", "url": "https://store.example.com", "type": "ecommerce"})
    .capability("content")
    .capability("commerce", {"endpoint": "/ai2w/products", "checkout": True})
    .capability("search", {"endpoint": "/ai2w/search"})
    .transports({"mcp": {"enabled": True, "endpoint": "/ai2w/mcp"}, "rest": {"enabled": True, "base": "/ai2w"}})
    .auth({"methods": ["none", "oauth2"], "oauth2": {"pkce": True, "scopes": ["checkout"]}})
    .consent({"requires_user_approval_for": ["purchase"]})
    .events({"endpoint": "/ai2w/events", "types": ["order.shipped", "price.drop"]})
    .action({"name": "track_order", "description": "Track", "method": "POST", "endpoint": "/ai2w/actions/track-order",
             "requires_auth": True, "requires_user_approval": False, "risk": "medium", "input_schema": {"type": "object"}})
    .identity({"legal_name": "Example Store Ltd"})
    .contact({"support": "help@store.example.com"})
    .build()
)
check(m["protocol"] == "ai2w", "builder sets protocol ai2w")

v = validate(m)
check(v["valid"] is True, "manifest is valid", v["errors"])
check(v["score"] >= 90, "AI Readiness score >= 90", v["score"])
check(v["tier"] in ("Standard", "Enterprise"), "tier Standard/Enterprise", v["tier"])

# --- negotiate ---
neg = negotiate(m, {"transports": ["mcp", "rest"], "capabilities": ["content", "commerce", "flying"], "auth": ["oauth2"]})
check(neg["negotiated"]["transport"] == "mcp", "negotiate picks mcp", neg["negotiated"]["transport"])
check(neg["negotiated"]["capabilities"] == ["content", "commerce"], "negotiate intersects caps", neg["negotiated"]["capabilities"])
check(neg["unsupported"] == ["flying"], "negotiate reports unsupported", neg["unsupported"])
check(neg["negotiated"]["auth"] == "oauth2", "negotiate selects oauth2", neg["negotiated"]["auth"])

# --- server routing ---
home = handle({"manifest": m}, "GET", "/ai2w")
check(home["status"] == 200 and home["body"]["protocol"] == "ai2w", "server serves manifest at /ai2w")
wk = handle({"manifest": m}, "GET", "/.well-known/ai2w", None, "https://store.example.com")
check(wk["body"]["ai2w"] == "https://store.example.com/ai2w", "well-known returns pointer", wk["body"])
notget = handle({"manifest": m}, "POST", "/ai2w")
check(notget["status"] == 405, "manifest is GET-only (405 on POST)")
act = handle({"manifest": m, "actions": {"track_order": lambda b: {"ok": True, "echo": b}}}, "POST", "/ai2w/actions/track-order", {"order_id": "A1"})
check(act["body"]["ok"] is True, "server dispatches action handler", act["body"])

# --- SSRF guard ---
check(is_safe_public_url("https://store.example.com") is True, "ssrf allows public https")
check(is_safe_public_url("http://169.254.169.254/latest") is False, "ssrf blocks metadata ip")
check(is_safe_public_url("http://localhost:8080") is False, "ssrf blocks localhost")
check(is_safe_public_url("https://10.0.0.5/x") is False, "ssrf blocks private range")

# --- conformance contract (parity with the spec) ---
cases = json.load(open(os.path.join(os.path.dirname(__file__), "conformance_cases.json")))
for c in cases:
    r = validate(c["manifest"])
    e = c["expect"]
    probs = []
    if "valid" in e and r["valid"] != e["valid"]:
        probs.append(f"valid={r['valid']}")
    if "tier" in e and r["tier"] != e["tier"]:
        probs.append(f"tier={r['tier']} (want {e['tier']})")
    if "minScore" in e and r["score"] < e["minScore"]:
        probs.append(f"score={r['score']} < {e['minScore']}")
    if "errorsContain" in e and not any(e["errorsContain"] in x for x in r["errors"]):
        probs.append(f"errors missing '{e['errorsContain']}'")
    if "warns" in e:
        for w in e["warns"]:
            chk = next((c2 for c2 in r["checks"] if c2["label"] == w), None)
            if not chk or chk["ok"]:
                probs.append(f"expected warn '{w}'")
    check(not probs, "conformance: " + c["name"], probs or None)

# --- request validation (validate_schema + server) ---
_s = {"type": "object", "properties": {"order_id": {"type": "string"}, "qty": {"type": "integer"}}, "required": ["order_id"]}
check(validate_schema({"order_id": "A1", "qty": 2}, _s).valid, "schema: valid input passes")
check(not validate_schema({"qty": 2}, _s).valid, "schema: missing required fails")
check(not validate_schema({"order_id": 5}, _s).valid, "schema: wrong type fails")
check(not validate_schema({"order_id": "A1", "qty": 1.5}, _s).valid, "schema: non-integer fails")
check(validate_schema({"anything": 1}, {}).valid, "schema: empty schema accepts anything")

_man = {
    "protocol": "ai2w", "version": "0.1",
    "site": {"name": "S", "url": "https://s.example", "type": "ecommerce"},
    "capabilities": {"actions": {"enabled": True}},
    "actions": [{
        "name": "track_order", "method": "POST", "endpoint": "/ai2w/actions/track-order",
        "requires_auth": False, "requires_user_approval": False, "risk": "low",
        "input_schema": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]},
    }],
}
_acts = {"track_order": lambda b: {"ok": True}}
_ok = handle({"manifest": _man, "actions": _acts}, "POST", "/ai2w/actions/track-order", {"order_id": "A1"})
_bad = handle({"manifest": _man, "actions": _acts}, "POST", "/ai2w/actions/track-order", {})
_off = handle({"manifest": _man, "actions": _acts, "validate_input": False}, "POST", "/ai2w/actions/track-order", {})
check(_ok["status"] == 200, "server: valid body -> 200", _ok)
check(_bad["status"] == 400 and _bad["body"]["error"]["code"] == "invalid_request", "server: missing required -> 400 invalid_request", _bad["body"])
check(_off["status"] == 200, "server: validate_input=False opt-out passes through", _off)

# --- v0.2 modules + export adapters (parity with @ai2web/core) ---
m2 = (
    ai2web({"name": "Example Bistro", "url": "https://bistro.example", "type": "restaurant",
            "description": "Italian, terrace dining."})
    .capability("content")
    .capability("commerce", {"endpoint": "/ai2w/products"})
    .capability("search", {"endpoint": "/ai2w/search"})
    .action({"name": "book_table", "description": "Reserve a table.", "method": "POST",
             "endpoint": "/ai2w/actions/book-table", "requires_auth": False, "requires_user_approval": True,
             "risk": "medium", "intent": "reserve_table",
             "input_schema": {"type": "object", "properties": {"date": {"type": "string"}, "party": {"type": "integer"}},
                              "required": ["date", "party"]},
             "bindings": [{"kind": "mcp", "ref": "book_table", "priority": 1},
                          {"kind": "redirect", "ref": "/reserve", "priority": 9, "fallback_only": True}]})
    .knowledge([{"id": "menu", "name": "Menu", "kind": "catalog", "ref": "/ai2w/products", "format": "json"}])
    .governance({"rate_limits": {"requests": 60, "window_seconds": 60}, "consent_mode": {"book_table": "explicit"}})
    .usage_policy({"bulk_extraction": False, "model_training": False})
    .legal({"jurisdiction": "EU", "ai_transparency": True, "ai_risk_classification": "limited"})
    .agent_identity({"required": False, "allow_anonymous": True, "methods": ["http_message_signatures"]})
    .contact({"support": "hi@bistro.example"})
    .build()
)
check(m2["version"] == "0.2", "builder defaults to version 0.2", m2["version"])
check(m2["governance"]["rate_limits"]["requests"] == 60, "builder: governance")
check(m2["usage_policy"]["model_training"] is False, "builder: usage_policy")
check(m2["legal"]["ai_risk_classification"] == "limited", "builder: legal")
check(m2["identity"]["agent"]["methods"][0] == "http_message_signatures", "builder: agent identity")
check(m2["knowledge"][0]["id"] == "menu", "builder: knowledge")
check(m2["actions"][0]["intent"] == "reserve_table", "action: intent")
check(len(m2["actions"][0]["bindings"]) == 2, "action: bindings")
check(m2["actions"][0]["bindings"][1]["fallback_only"] is True, "action: fallback_only binding")

txt = to_llms_txt(m2)
check(txt.startswith("# Example Bistro"), "llms.txt: title")
check("## Capabilities" in txt and "- commerce" in txt, "llms.txt: capabilities")
check("## Knowledge" in txt and "Menu" in txt, "llms.txt: knowledge")
check("book_table: Reserve a table." in txt, "llms.txt: action")
check("https://bistro.example/ai2w" in txt, "llms.txt: discovery link")

aj = to_agent_json(m2)
check(aj["name"] == "Example Bistro", "agent.json: name")
check("commerce" in aj["capabilities"], "agent.json: capabilities")
check(aj["actions"][0]["intent"] == "reserve_table", "agent.json: action intent")
check(len(aj["actions"][0]["bindings"]) == 2, "agent.json: bindings preserved")
check(aj["policies"]["legal"]["jurisdiction"] == "EU", "agent.json: legal in policies")
check(aj["policies"]["governance"]["consent_mode"]["book_table"] == "explicit", "agent.json: governance carried")
# action without explicit bindings falls back to a rest binding on its endpoint
_aj_default = to_agent_json(ai2web({"name": "X", "url": "https://x.example", "type": "site"})
                            .action({"name": "a", "description": "d", "method": "POST", "endpoint": "/ai2w/actions/a",
                                     "requires_auth": False, "requires_user_approval": False, "risk": "low"}).build())
check(_aj_default["actions"][0]["bindings"][0]["kind"] == "rest", "agent.json: default rest binding")

# --- multi-surface serving (llms.txt + agent.json) ---
_srv = {"manifest": m2}
_llms = handle(_srv, "GET", "/llms.txt")
check(_llms["status"] == 200 and _llms["headers"]["content-type"].startswith("text/plain"), "server: /llms.txt text/plain", _llms["status"])
check(isinstance(_llms["body"], str) and _llms["body"].startswith("# Example Bistro"), "server: /llms.txt body")
_ajr = handle(_srv, "GET", "/.well-known/agent.json")
check(_ajr["status"] == 200 and _ajr["body"]["name"] == "Example Bistro", "server: /.well-known/agent.json", _ajr["status"])
_ajr2 = handle(_srv, "GET", "/agent.json")
check(_ajr2["status"] == 200 and _ajr2["body"]["policies"]["governance"]["rate_limits"]["requests"] == 60, "server: /agent.json alias + governance")
_llpost = handle(_srv, "POST", "/llms.txt")
check(_llpost["status"] == 405, "server: /llms.txt POST -> 405")

print("\n" + ("ALL PASS" if failures == 0 else f"{failures} FAILED"))
sys.exit(0 if failures == 0 else 1)
