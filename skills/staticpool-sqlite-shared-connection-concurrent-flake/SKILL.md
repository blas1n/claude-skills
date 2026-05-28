---
name: staticpool-sqlite-shared-connection-concurrent-flake
description: A StaticPool :memory: SQLite test engine forces ALL sessions onto ONE shared connection. Tests that drive two sessions concurrently (e.g. an orchestrator + a simulated worker) then contend on that single connection, serializing unpredictably under CI load — a system_error/timeout flake that never reproduces locally. Use a file-backed SQLite + WAL so each session gets its own connection, like prod.
---

# StaticPool :memory: shared-connection concurrent-session flake

## Problem

A common async-SQLAlchemy test harness shares an in-memory DB across sessions with `StaticPool`:

```python
engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,   # <-- forces ONE shared DBAPI connection
)
```

`StaticPool` is *required* for `:memory:` to be shared (a fresh `:memory:` connection is an empty DB), so it's the obvious choice. But it means **every** session checked out of the pool uses the **same single connection**.

This is fine for sequential tests. It breaks when a test drives **two sessions concurrently** — e.g. an orchestrator coroutine (`oc.run`) plus a simulated worker coroutine that commits a result on its "separate" session:

```python
drive_task  = asyncio.create_task(oc.run(...))        # session A
worker_task = asyncio.create_task(simulate_worker())   # session B — SAME connection
```

Sessions A and B both run their transactions through the **one** aiosqlite connection (single background thread, serialized). Their interleaving is timing-dependent:
- **Symptom 1 (flake):** under CI load the worker's result-commit gets starved/serialized past an await/poll timeout → the awaiter raises a timeout that surfaces as `system_error` / a wrong terminal outcome. **Never reproduces locally** (load + scheduling dependent) — green 40×/full-suite locally, red intermittently on CI.
- **Symptom 2 (if you add more DB access):** `StaleDataError: UPDATE ... expected to update 1 row(s); 0 were matched` — extra sessions reading on the shared connection corrupt the in-flight transaction's view.

## Solution

Give each session its **own connection** — exactly like prod (every session has a distinct connection). For SQLite that means a **file-backed** DB (not `:memory:`) with the default pool, in **WAL** mode so a reader and a writer coexist:

```python
import tempfile
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

db_path = Path(tempfile.mkdtemp(prefix="myapp-test-")) / "test.db"
engine = create_async_engine(
    f"sqlite+aiosqlite:///{db_path}",
    connect_args={"check_same_thread": False},
)

@event.listens_for(engine.sync_engine, "connect")
def _sqlite_pragmas(dbapi_conn, _record):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")   # reader + writer coexist
    cur.execute("PRAGMA busy_timeout=5000")  # wait out the brief write lock, don't error
    cur.close()
```

Now the orchestrator session and the worker session hold **independent** connections; WAL lets the worker commit while the orchestrator polls, without `database is locked`. The flake's root (single-connection contention) is gone.

## Key Insights

- **`StaticPool` + `:memory:` = one connection for ALL sessions.** It silently models something prod never does (prod = one connection per session). Any test that exercises *concurrent* sessions on that engine is testing an unrealistic, fragile topology.
- **A flake that won't reproduce locally but recurs on CI is usually load/scheduling-sensitive** — single-connection serialization, event-loop contention, or timing races. Don't keep re-running; find the *structural* fragility.
- **Don't ship a speculative prod fix for a flake you can't reproduce.** It violates TDD (no failing test) and often misdiagnoses. Reproduce, or correct your hypothesis, first. (Here the initial "cross-session DB snapshot" hypothesis was wrong: SQLite legacy isolation doesn't pin SELECT snapshots and prod Postgres is READ COMMITTED — the prod code was fine all along.)
- **WAL + busy_timeout is the standard combo** for file-SQLite tests with any concurrency.

## Red Flags

- Test helper named like `_shared_sessionmaker` using `poolclass=StaticPool` + `:memory:`.
- A test does `asyncio.create_task(...)` for two coroutines that each open their own session against that engine.
- CI flakes on `assert <terminal_state> == <expected>` (e.g. `'system_error' == 'needs_decision'`) or an await/poll **timeout**, only under the full suite / coverage run, never in isolation.
- Adding any extra DB read to such a test triggers `StaleDataError` — the smoking gun for shared-connection transaction corruption.

## When this fired

BSVibe executor tests (2026-05-28): `tests/executors/test_orchestrator.py` B2b tests drive `oc.run` + a simulated worker concurrently on a `StaticPool` `:memory:` engine. Recurring `system_error` flake (`await_completion` 30s timeout) across ~5 PRs, never reproducible locally (40× iso, full-suite+cov all green). A DB-poll "fix" attempt produced `StaleDataError`, confirming the single-connection hazard. Switching `_shared_sqlite_sessionmaker` to a per-call file-backed WAL engine (each session its own connection) removed the contention. Test-harness only — no prod code changed (prod was never affected: PG READ COMMITTED).
