---
name: fastapi-app-state-fallback-trap
description: "FastAPI app.state getattr fallback creates detached default — mutations lost to garbage collection"
version: 1.0.0
---

# FastAPI app.state getattr Fallback Trap

**Problem**: Using `getattr(request.app.state, "attr", default_mutable)` to defensively access optional app state creates a **detached default** — the fallback value is never stored back on `app.state`, so any mutations to it (like adding tasks to a set) are lost to garbage collection.

**When it happens**: Hardening code that accesses `app.state` attributes which may not exist in all environments (tests, alternate startup paths).

## The Trap

```python
# ❌ WRONG — if "background_tasks" doesn't exist, creates a NEW empty set
# that is never stored on app.state. Tasks added to it get GC'd immediately.
bg_tasks: set = getattr(request.app.state, "background_tasks", set())
task = asyncio.create_task(some_coro())
bg_tasks.add(task)  # Added to ephemeral set → task reference lost → GC'd
task.add_done_callback(bg_tasks.discard)  # Callback on a potentially dead task
```

The `getattr` fallback `set()` is constructed fresh on every call. It's never assigned to `app.state`, so the task set evaporates after the function returns.

## Why Direct Access Also Fails

```python
# ❌ ALSO WRONG — fails in tests where app.state doesn't have the attribute
bg_tasks: set = request.app.state.background_tasks  # AttributeError in tests!
```

Test fixtures that create minimal app state (e.g., `app.state.db_pool = MagicMock()`) often omit optional attributes like `background_tasks`, causing `AttributeError` at runtime.

## Correct Pattern: Lazy Init with hasattr

```python
# ✅ CORRECT — lazy-init ensures the set is stored on app.state
if not hasattr(request.app.state, "background_tasks"):
    request.app.state.background_tasks = set()
bg_tasks: set = request.app.state.background_tasks
task = asyncio.create_task(some_coro())
bg_tasks.add(task)
task.add_done_callback(bg_tasks.discard)
```

This works in both production (where lifespan already sets it) and tests (where it's lazily created on first use).

## General Rule

> Never use `getattr(obj, attr, mutable_default)` when you intend to **mutate** the result.
> The mutable default is detached from the source object — mutations are silently lost.

This applies to any mutable default: `set()`, `[]`, `{}`, `defaultdict(...)`.

## Checklist

- [ ] If the fallback value is mutable AND will be mutated, use `hasattr` + assignment instead of `getattr`
- [ ] If the attribute MUST exist (set in lifespan/startup), use direct access — but ensure test fixtures also set it
- [ ] If using lazy init pattern, put the `hasattr` check before every access point (not just one)
