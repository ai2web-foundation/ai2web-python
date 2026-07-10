# AI2Web Python SDK (`ai2web`)

The Python reference implementation of the [AI2Web protocol](https://github.com/ai2web-foundation/ai2web-spec) - for Django, Flask, FastAPI, or plain Python. Mirrors `@ai2web/core`.

```python
from ai2web import ai2web, validate, handle

manifest = (
    ai2web({"name": "Example Store", "url": "https://example.com", "type": "ecommerce"})
    .capability("content")
    .capability("commerce", {"endpoint": "/ai2w/products", "checkout": True})
    .transports({"mcp": {"enabled": True, "endpoint": "/ai2w/mcp"}, "rest": {"enabled": True}})
    .auth({"methods": ["none", "oauth2"], "oauth2": {"pkce": True, "scopes": ["checkout"]}})
    .consent({"requires_user_approval_for": ["purchase"]})
    .contact({"support": "help@example.com"})
    .build()
)

result = validate(manifest)          # {'score': 90+, 'tier': 'Standard', ...}

# Serve every AI2Web route from one call (framework-agnostic):
res = handle({"manifest": manifest}, method, path, body, origin)
```

## Modules
- `ai2web.manifest` - fluent capability-model builder (`ai2web(...)`, `Manifest`).
- `ai2web.validator` - `validate()` + AI Readiness scoring (spec §9/§11).
- `ai2web.negotiator` - `negotiate()` capability negotiation (spec §5).
- `ai2web.server` - `handle()` framework-agnostic route handler.
- `ai2web.safety` - `is_safe_public_url()` / `assert_safe_public_url()` SSRF guard.

## Test
```bash
python tests/run.py     # dependency-free; includes the shared conformance contract
```

Requires **Python 3.9+**. Zero runtime dependencies.

## Licence
MIT.
