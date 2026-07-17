"""Fluent AI2Web (ai2w) manifest builder - 'describe your website once'."""

from __future__ import annotations

from typing import Any, Dict, List, Union
import json


class Manifest:
    def __init__(self, site: Dict[str, Any]):
        self._m: Dict[str, Any] = {"protocol": "ai2w", "version": "0.2", "site": site, "capabilities": {}}

    @classmethod
    def for_site(cls, name: str, url: str, type: str, **extra: Any) -> "Manifest":
        return cls({"name": name, "url": url, "type": type, **extra})

    def capability(self, name: str, value: Union[bool, Dict[str, Any]] = True) -> "Manifest":
        if isinstance(value, dict):
            value = {"enabled": True, **value}
        self._m["capabilities"][name] = value
        return self

    def transports(self, t: Dict[str, Any]) -> "Manifest":
        self._m.setdefault("transports", {}).update(t)
        return self

    def auth(self, a: Dict[str, Any]) -> "Manifest":
        self._m["auth"] = a
        return self

    def consent(self, c: Dict[str, Any]) -> "Manifest":
        self._m["consent"] = c
        return self

    def action(self, a: Dict[str, Any]) -> "Manifest":
        self._m.setdefault("actions", []).append(a)
        self.capability("actions", {"endpoint": "/ai2w/actions"})
        return self

    def events(self, e: Dict[str, Any]) -> "Manifest":
        self._m["events"] = e
        self.capability("events", {"endpoint": e.get("endpoint", "/ai2w/events")})
        return self

    def agent_service(self, s: Dict[str, Any]) -> "Manifest":
        self._m["agent_service"] = s
        return self

    def identity(self, i: Dict[str, Any]) -> "Manifest":
        self._m["identity"] = i
        return self

    def contact(self, c: Dict[str, Any]) -> "Manifest":
        self._m["contact"] = c
        return self

    # v0.2 optional modules (all additive; a minimal manifest stays valid without them).
    def governance(self, g: Dict[str, Any]) -> "Manifest":
        self._m["governance"] = g
        return self

    def usage_policy(self, u: Dict[str, Any]) -> "Manifest":
        self._m["usage_policy"] = u
        return self

    def legal(self, l: Dict[str, Any]) -> "Manifest":
        self._m["legal"] = l
        return self

    def agent_identity(self, a: Dict[str, Any]) -> "Manifest":
        self._m["identity"] = {**(self._m.get("identity") or {}), "agent": a}
        return self

    def knowledge(self, k: List[Dict[str, Any]]) -> "Manifest":
        self._m["knowledge"] = k
        return self

    def extend(self, key: str, value: Any) -> "Manifest":
        if not key.startswith("x-"):
            key = "x-" + key
        self._m[key] = value
        return self

    def build(self) -> Dict[str, Any]:
        return self._m

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self._m, indent=indent)


def ai2web(site: Dict[str, Any]) -> Manifest:
    return Manifest(site)
