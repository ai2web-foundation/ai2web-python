"""NLWeb (nlweb.ai) interop primitives.

NLWeb turns a site's content into a natural-language, schema.org-flavoured query endpoint (its
``ask`` API). This module lets an AI2Web site advertise an NLWeb surface in its manifest and serve
a minimal, NLWeb-compatible ``ask`` response over its own content, so agents that speak NLWeb can
query the site without it deploying the full NLWeb stack.

The search itself is application-specific (this is a pure toolkit): the app finds the matching
content items and passes them in; :func:`ask_response` shapes them into NLWeb's result envelope
(``list`` mode, schema.org ``Item`` results; pass ``answer`` for ``generate`` mode). NLWeb defines
no discovery file, so :func:`transport` is an AI2Web convention pointing at the site's ``/ask``
(and ``/mcp``) URLs.
"""

from __future__ import annotations

import secrets
from typing import Any, Dict, List, Optional

VERSION = "0.55"
_DEFAULT_ASK = "/ai2w/nlweb/ask"
_DEFAULT_MCP = "/ai2w/nlweb/mcp"


def transport(overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The ``transports.nlweb`` advertisement to merge into a manifest."""
    block = {
        "enabled": True,
        "version": VERSION,
        "ask": _DEFAULT_ASK,
        "mcp": _DEFAULT_MCP,
        "modes": ["list"],
    }
    if overrides:
        block.update(overrides)
    return block


def item(content: Dict[str, Any], *, site: Optional[str] = None, site_url: Optional[str] = None) -> Dict[str, Any]:
    """Wrap one content item into an NLWeb result ``Item``."""
    schema = content.get("schema_object")
    return {
        "@type": "Item",
        "url": str(content.get("url", "")),
        "name": str(content.get("name", content.get("title", ""))),
        "site": str(content.get("site", site or "")),
        "siteUrl": str(content.get("siteUrl", site_url or "")),
        "score": int(content["score"]) if "score" in content else 100,
        "description": str(content.get("description", "")),
        "schema_object": schema if isinstance(schema, dict) else _schema_object(content),
    }


def ask_response(
    query: str,
    items: List[Dict[str, Any]],
    *,
    site: Optional[str] = None,
    site_url: Optional[str] = None,
    query_id: Optional[str] = None,
    answer: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a minimal buffered NLWeb ``ask`` response (list mode) from matched content items."""
    results = [item(it if isinstance(it, dict) else {}, site=site, site_url=site_url) for it in items]
    resp: Dict[str, Any] = {
        "query": query,
        "query_id": query_id or ("q_" + secrets.token_hex(8)),
        "message_type": "result",
        "results": results,
    }
    if answer:
        resp["answer"] = {"@type": "GeneratedAnswer", "answer": str(answer), "items": results}
    return resp


def _schema_object(c: Dict[str, Any]) -> Dict[str, Any]:
    obj: Dict[str, Any] = {"@type": str(c.get("type", "Thing"))}
    name = c.get("name") or c.get("title")
    if name:
        obj["name"] = name
    if c.get("url"):
        obj["url"] = c["url"]
    if c.get("description"):
        obj["description"] = c["description"]
    return obj
