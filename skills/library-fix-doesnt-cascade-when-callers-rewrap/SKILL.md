# Library fix doesn't cascade when callers re-wrap the dispatch

## When this applies

A bug surfaces in a shared library's high-level dispatch helper (e.g. `bsvibe_authz.deps.get_current_user`). You fix it in the library and bump every consumer's pinned ref. You expect the bug to disappear everywhere.

It doesn't, because callers don't actually use the high-level helper — they re-implement their own dispatch around the library's lower-level primitives (`verify_bootstrap_token`, `verify_opaque_token`, `verify_user_jwt`). The library fix is correct, but each consumer needs its own mirror fix.

## How to spot the trap before you ship

Before declaring a library fix sufficient:

1. Grep every consumer for the lower-level primitives, not the high-level helper. If callers use the primitives directly, they are re-implementing dispatch and need their own fix.
2. Search for repeated structural code across consumers (token prefix dispatch, error handling chains, etc.). Repetition is the smell.
3. Check for product-specific adapters / context types (`GatewayAuthContext`, `BSVibeUser`, etc.) — these are the reason callers re-wrap, and they almost guarantee dispatch logic was duplicated.

## What to do when you find it

- Open one PR per consumer that mirrors the library fix in their dispatch.
- Cross-reference the library PR in each consumer PR description.
- In the library PR, note that the fix won't cascade and list the consumers that need mirror PRs.
- Optionally, expose the new behavior as a reusable helper (e.g. `try_pat_jwt_via_introspection`) so future consumers can call it instead of re-implementing.

## Concrete instance

**2026-05-09**: PAT JWT introspection fallback for BSVibe Phase 1 token cutover.

- Library fix: `bsvibe-python#21` added introspection fallback to `bsvibe_authz.deps.get_current_user` when `verify_user_jwt` fails on a JWT-shaped token.
- E2E still failed against BSGateway with "Invalid token: Signature verification failed" until `BSGateway#45` added the same fallback to `bsgateway/api/deps.py::get_auth_context` (BSGateway has its own dispatch returning `GatewayAuthContext` with tenant resolution).
- `BSNexus#76` needed the same fix in `backend/src/core/auth.py::_dispatch_token` (returns `BSVibeUser`).
- BSage and BSupervisor have the same shape and would need the same fix in their own dispatch.

## Why callers re-wrap

Common reasons:

1. **Product-specific return type**: lib returns a generic `User`, caller needs a richer context (`tenant_id`, `is_admin`, app_metadata mapping).
2. **Side effects**: caller wants to verify the tenant is active, auto-provision rows, log audit events around auth.
3. **Legacy adapter**: caller still has a pre-migration auth provider (e.g. `bsvibe_auth.AuthProvider`) chained alongside the new path.
4. **Different framework**: lib helper is FastAPI-Depends-shaped, caller is Starlette/middleware/CLI.

When you write the library fix, ask: "would I add this fix to each call site, or to one shared helper?" If the answer is "each", you're already in this trap.
