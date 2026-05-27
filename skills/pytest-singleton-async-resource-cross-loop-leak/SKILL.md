---
name: pytest-singleton-async-resource-cross-loop-leak
description: "process-wide singletons that bind async resources at app/worker startup leak Futures across per-test event loops under pytest-asyncio — guard the wire-up with PYTEST_CURRENT_TEST, conftest reset alone is NOT enough"
version: 1.0.0
triggers:
  - pattern: "test failure: 'got Future ... attached to a different loop' or 'Event loop is closed' from a redis/httpx/db client"
  - pattern: "downstream tests fail with mysterious state pollution after integration tests that call create_app() / startup wiring"
  - pattern: "process-wide singleton + redis.asyncio.from_url() / httpx.AsyncClient() / asyncpg pool wired at app startup"
category: test
---

# Pytest Singleton + Async Resource: Cross-Loop Leak

## The trap

You have:
1. A process-wide singleton in production code (`_BUS`, `_LIVE_BUS`, `_CLIENT`, …)
2. A wire-up function called once at startup that injects an async resource into it (`redis.asyncio.from_url()`, `httpx.AsyncClient()`, `asyncpg.create_pool()`, …)
3. Production startup site (e.g., `create_app()`, `run_workers()`) reads an env var and calls the wire-up

```python
# backend/api/main.py — looks innocent
def create_app() -> FastAPI:
    app = FastAPI(...)
    if settings.redis_url:
        client = redis.asyncio.from_url(settings.redis_url)
        set_live_event_bus_redis(client)   # binds into _BUS singleton
    return app
```

Tests that call `create_app()` (glue / integration tests) trigger the wire-up. Each test runs on its own event loop (pytest-asyncio `function`-scoped). The redis client's connection pool holds Futures tied to **that test's** event loop.

When the test ends, the loop closes. The singleton still has a reference to the now-defunct client. Later tests touch the singleton → `RuntimeError: got Future <Future pending> attached to a different loop` or `RuntimeError: Event loop is closed`.

## Why conftest reset is NOT enough

```python
# tests/conftest.py — tempting but insufficient
@pytest.fixture(autouse=True)
def _reset_singleton():
    _le._BUS = None
    yield
    _le._BUS = None
```

This clears the singleton **between** tests. But:
- The wire-up runs **inside** the test body (in `create_app()`)
- So during the test the singleton gets re-bound to a fresh real client
- Tied to the current loop, which then closes at teardown
- Conftest sets `_BUS = None` after — but any code path that reaches the singleton **during the next test** is fine
- The leak surfaces only when a *subsequent* test's code (often an unrelated audit-emit, background task, or signal handler) holds a stale reference *across* the loop transition

The conftest reset hides the bug for serial isolated tests and exposes it for parallel / interleaved patterns. Symptoms shift around (different tests fail on different runs), looking like a flake.

## Symptom signature

In CI logs (often only in CI, not locally):

```
RuntimeError: Task <Task ...> got Future <Future pending> attached to a different loop
  File ".../redis/asyncio/connection.py", line 754, in read_response
    await self.disconnect(nowait=True)
  File ".../redis/asyncio/connection.py", line 585, in disconnect
    self._writer.close()
  File ".../asyncio/streams.py", line 358, in close
    return self._transport.close()
RuntimeError: Event loop is closed
```

The traceback often goes through `redis.publish` / `httpx._send` / pool teardown — code paths that the failing test doesn't directly call, because the resource was bound by an **earlier** test's wire-up.

Downstream effect: the singleton's leaked error bubbles through `await` chains. In one case (BSVibe C2 SSE lift) it surfaced as `executor outcome == "system_error"` instead of `"needs_decision"` — the bridge call escaped via `safe_emit`'s outer `try`, the orchestrator caught it, and a Decision path got flipped to `system_error`.

## The fix: guard wire-up with PYTEST_CURRENT_TEST

```python
# backend/api/main.py
import os

def create_app() -> FastAPI:
    app = FastAPI(...)
    # Skip under pytest: glue tests instantiate create_app() per-test on
    # per-test event loops, and binding a real client into the process-
    # wide singleton leaks connection-pool Futures across event loops.
    if settings.redis_url and not os.environ.get("PYTEST_CURRENT_TEST"):
        client = redis.asyncio.from_url(settings.redis_url)
        set_live_event_bus_redis(client)
    return app
```

Apply at **every** wire-up site — `create_app()`, worker `run()`, lifespan handlers, signal handlers. One un-guarded site is enough to repoison.

Combined with the conftest reset, this gives you: production unchanged, tests stay in the in-memory fallback path, no cross-loop leak.

## Why `PYTEST_CURRENT_TEST` (not a custom env)

- Pytest sets it automatically for every test (`<file>::<test> (call)`), unsets between
- No conftest plumbing required
- Works with any test runner that delegates to pytest
- Distinct from `TESTING=1` or `ENV=test` which production code already inspects for other reasons — `PYTEST_CURRENT_TEST` is unambiguously *only* set when a test is currently running

## Generalization

This pattern applies to **any** process-wide singleton holding an async resource:

| Resource | Wire-up call | Symptom |
|---|---|---|
| `redis.asyncio.Redis` | `from_url(...)` at startup | publish/pubsub cross-loop RuntimeError |
| `httpx.AsyncClient` | `AsyncClient()` in module | `RuntimeError: client has been closed` or pool Future leak |
| `asyncpg.Pool` | `create_pool()` at startup | `the pool is closed` / connection cross-loop error |
| `aiohttp.ClientSession` | constructed at startup | `Cannot connect to host` after first test |
| Long-lived `asyncio.Task` (relay, listener, watcher) | spawned during wire-up | task gets cancelled mid-flight, errors escape |

If your prod code constructs an async resource and stores it in a module global / class attribute / DI container that survives `create_app()`, the same guard applies.

## Detection checklist

When you see cross-loop / closed-loop errors **only in CI** or **only after a specific test ran first**:

1. `grep -rn "from_url\|AsyncClient\|create_pool\|asyncio.create_task" backend/ | grep -i "app\|main\|run\|startup"` — find wire-up sites
2. Check if those sites have a singleton write (`global _X`, module attribute assignment, DI container set)
3. Check if tests trigger them (`grep -rn "create_app()\|run_workers()" tests/`)
4. Check if CI sets the env var that gates the wire-up (e.g., `BSVIBE_REDIS_URL: redis://...` in `ci.yml`) — locally unset, that's why it doesn't repro
5. Add `PYTEST_CURRENT_TEST` guard at every wire-up site

## Local reproduction tip

Local `pytest` often passes because the wire-up only fires when `BSVIBE_REDIS_URL` (or equivalent) is set. To reproduce CI's behavior locally:

```bash
BSVIBE_REDIS_URL=redis://localhost:6379/0 \
  uv run pytest tests/ --cov=backend --cov-report=
```

Coverage instrumentation slows scheduling enough to widen the race window and often surfaces the bug that ran-fine-without-coverage hides.

## Related skills / traps

- [[pytest-coverage-gotchas]] — coverage instrumentation slows scheduling and exposes races
- [[asyncpg-testing-patterns]] — sibling pattern: mock at repo level, not at pool/connection level
- [[eventsource-sse-auth-trap]] — same project (BSVibe) — SSE infrastructure that surfaced this trap when lifted cross-process

## Lift origin

BSVibe C2 SSE Redis bus lift (2026-05-27): added `from backend.api.v1.live_events import set_live_event_bus_redis` wire-up to `create_app()` and `run_workers()`. CI began failing intermittently with `system_error == needs_decision` on executor orchestrator tests downstream of glue tests. Traceback eventually showed redis publish on a closed loop. Two earlier fix attempts (outer try/except in producer, conftest singleton reset) reduced but did not eliminate failures. The third attempt — PYTEST_CURRENT_TEST guard at both wire-up sites — fixed it deterministically. See PR #146 (cd57f52) for the final landed fix.
