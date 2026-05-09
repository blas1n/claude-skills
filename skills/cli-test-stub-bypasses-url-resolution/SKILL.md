# CLI test stub bypasses URL resolution → hardcoded prefix double-applies in prod

## When this applies

A CLI / SDK / HTTP wrapper transforms input at construction time — for example:

- Auto-prepending a base path: `_resolve_base_url(url) → url + "/api/v1"`
- Injecting an `Authorization` header from a profile / keyring
- Adding a tenant query param
- Resolving a JWKS URL from an issuer

Tests stub the wrapper with a **bare, un-transformed value** so they don't have to wire the transformation:

```python
def _build(_ctx) -> CliHttpClient:
    return CliHttpClient(
        base_url="http://test",     # ← no /api/v1 prefix
        http=ASGITransport(app=app),
    )
```

If command/handler code hardcodes the same transformation it expects from the wrapper:

```python
async def projects_list(...):
    path = "/api/v1/projects"        # ← hardcoded prefix
    return await client.get(path)
```

The bug is invisible in tests:

- **In tests**: stub base_url is `http://test`. Path `/api/v1/projects` joins to `http://test/api/v1/projects`. The test ASGI app has `/api/v1/projects` mounted. **200**.
- **In prod**: real wrapper resolves `--url http://host` → `http://host/api/v1`. Path `/api/v1/projects` joins to `http://host/api/v1/api/v1/projects`. **404**.

**The CI/test suite is 100% green and the binary 404s on every command in production.**

## Trigger signals

Watch for this when you see:

1. A "convenience" wrapper that transforms construction args (URL append, header injection, default param fill).
2. Test factories that build the wrapper with a **bare** (un-transformed) value — comments often justify this with "to keep the test simple" or "TestClient base URL is just `http://test`".
3. Command/handler code referencing the same transformation literal (e.g. `/api/v1` appears in both `_resolve_base_url` and command paths).

The combination of any two of these is the trap. The third confirms it's already broken.

## Defenses

**Option A — Mirror the real transformation in the stub.**

```python
def _build(_ctx) -> CliHttpClient:
    # Mirror _resolve_base_url so the ASGITransport sees the same URL
    # shape the real CliHttpClient produces.
    return CliHttpClient(base_url="http://test/api/v1", ...)
```

This is the smallest fix when you can't refactor commands.

**Option B — Move the transformation OUT of construction and INTO a single chokepoint.**

If `_resolve_base_url` is supposed to be the single source of truth, command paths must NOT include the prefix. The convention in BSGateway works:

```python
# bsgateway/cli/_client.py
def build_client(ctx) -> CliHttpClient:
    return CliHttpClient(base_url=_resolve_base_url(ctx.url), ...)

# bsgateway/cli/commands/models.py
async def list_models():
    return await client.get("/admin/models")   # NO /api/v1
```

Command paths are bare; the wrapper owns the prefix. Tests stub the wrapper output and the stub's base_url is bare too — symmetric.

**Option C — Real-backend integration test.**

A single e2e test that boots the actual backend and runs the actual CLI against it catches this in 30 seconds. The unit suite can have any number of holes; the integration test proves the wire format.

## Why CI didn't save you

CI runs the unit suite. Unit suite stubs the transformation. Stub's `base_url` is naturally bare because that's what TestClient/ASGI expects. The hardcoded prefix in command code coincidentally lines up with the bare stub's URL shape. Green ✓.

The only way unit tests catch this is if the stub mirrors production's transformation faithfully — which most authors don't bother to do because it feels redundant.

## Concrete instance

**2026-05-09**: BSNexus CLI follow-up to PR #76.

- PR #76 added `_resolve_base_url(url)` that auto-appends `/api/v1` to `ctx.url`.
- Every command module still had `path = "/api/v1/projects"` hardcoded.
- Unit tests in `test_cli_e2e.py::_wire_cli_client` stubbed `CliHttpClient(base_url="http://test")` (no prefix). The ASGI transport handled `/api/v1/projects` because the FastAPI app mounted routes at that path. Tests green.
- Real CLI invocation against the live e2e backend returned `HTTP 404 — Not Found` for every command.
- Discovered only when a production-level e2e scenario (P4) ran `bsnexus projects list` against the running container.
- Fix: 17 path literals stripped (`/api/v1/x` → `/x`) + test stub updated to `base_url="http://test/api/v1"` (mirror prod). 770 unit tests still pass; real CLI now 200.

## Related case — SPA catch-all masks unauth assertions

A symptom of the same family. When a backend serves both `/api/*` REST + `/*` SPA via a catch-all, hitting an `/api/` path that **doesn't match a registered route** falls through to the SPA handler and returns `200 + index.html`. Auth-required e2e tests probing such a path see `200` regardless of token validity → vacuous pass.

In this session, `S2` (bootstrap admin) probed `/api/knowledge/entries` on BSage; that path isn't a REST route at all, so the response was `200 index.html` whether or not the bootstrap token was valid. Switched to `/mcp/health` (real unauthenticated liveness probe) which has a defined handler.

**Defense**: when adding an auth-required probe, first verify the path appears in the backend's `/openapi.json` (or equivalent). If it doesn't, the test isn't testing what it claims.
