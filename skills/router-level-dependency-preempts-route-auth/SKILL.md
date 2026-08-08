---
name: router-level-dependency-preempts-route-auth
description: A FastAPI router mounted with a blanket `APIRouter(dependencies=[Depends(get_current_user)])` runs that check BEFORE any route-level dependency. Adding a broader auth resolver to one route under that router silently never executes — the request 401s from the router gate, and even a print() inside your resolver produces no output.
category: trap
---

# A router-level dependency preempts your route-level auth

## Problem

Gate an entire API version in one line — a common, good pattern:

```python
# backend/api/v1/__init__.py
router = APIRouter(prefix="/v1", dependencies=[Depends(get_current_user)])
```

Later, one route under it must accept a *second* credential class (a machine
token, an API key, a signed webhook). You add a resolver to that route:

```python
@v1_router.post("/pats")
async def create_pat(principal: Annotated[PatPrincipal, Depends(resolve_pat_principal)]):
    ...
```

It never runs. FastAPI evaluates the router's dependencies **first**, so the
blanket `get_current_user` rejects the machine token and returns 401 before your
resolver is reached.

Why it burns time: the 401 body is a *plausible* auth error from the gate
(`"user JWT verification failed: The specified alg value is not allowed"`), so it
reads like a bug in your new verifier. You then debug the resolver — checking
issuer discrimination, claim parsing, token minting — all of which are fine.

**The decisive symptom:** a `print()` / breakpoint inside your resolver produces
**no output at all**. Not wrong output — *none*. If your code did not execute,
stop debugging its logic and go look at what runs before it.

## Solution

### Diagnose

```python
# Temporarily, inside the resolver:
import sys; print(">>>DBG reached resolver", file=sys.stderr)
```

Silence ⇒ something upstream short-circuits. Find it:

```bash
grep -rn "APIRouter(" backend/api/ | grep dependencies=
grep -rn "include_router" backend/api/main.py
```

### Fix: mount the route on a sibling router, outside the gate

Do **not** widen the blanket dependency — that changes auth for every endpoint
under it. Mount a separate router at the same URL prefix instead:

```python
# Same /api/v1 path, but NOT under the v1 router's session-JWT gate: these
# routes authenticate themselves.
pats_router = APIRouter(prefix="/oauth", tags=["oauth"])

# main.py — order does not matter; paths are distinct.
app.include_router(pats_router, prefix="/api/v1")   # self-authenticating
app.include_router(v1_router, prefix="/api")        # blanket-gated
```

Mature codebases usually already do this for webhooks, SSE streams and worker
callbacks — look for a `*_public_router` and copy that seam rather than
inventing one.

### Then check what else the gate was silently providing

The blanket dependency may have been doing more than authentication. Here it
transitively pulled `get_workspace_id`, which sets the ORM auto-filter
contextvar **and** the Postgres RLS GUC. Leaving the gate means your resolver
must perform that publication itself:

```python
set_current_workspace_id(principal.workspace_id)
await set_workspace_guc(await session.connection(), principal.workspace_id)
```

Miss it and the routes still work — while being the one place tenant isolation
is advisory. A structural scope-audit test is what catches this; if the repo has
one, register your resolver as a scoping dependency rather than allow-listing
the routes (an allow-list entry asserts "legitimately global", which is false).

### Expect the existing tests to break — that is the design working

Tests that authenticated via `app.dependency_overrides[get_current_user]` now
bypass nothing, because your route no longer depends on it. Update them to send
a **real** token (HS256 dev mode makes this a two-line helper). That is a
strictly better test, not a workaround.

## Related

- `mock-fixtures-hide-wiring-bugs`
- `hook-prefix-matcher-skips-compound-command` — the same "it didn't run" reading trap
- `eventsource-sse-auth-trap` — another route that must live outside the gate
