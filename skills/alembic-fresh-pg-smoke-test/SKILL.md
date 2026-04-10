---
name: alembic-fresh-pg-smoke-test
description: "SQLite-only unit tests cannot catch PostgreSQL-only migration bugs. Add a fresh-PG smoke test that runs `alembic upgrade head` against an empty container so DROP DEFAULT, enum DDL listener collisions, and dependent-object errors fail at PR time instead of on the next dev's first bootstrap."
version: 1.0.0
---

# Alembic Fresh-PG Smoke Test

## When to Use

Any project where:
- Unit tests use **SQLite** (e.g. `aiosqlite`) for speed/isolation, **but**
- Production / target deployment runs **PostgreSQL**, **and**
- The same Alembic migration tree is supposed to apply to both.

If both halves are true, you have a **silent gap**: PG-only DDL semantics
(enum types, `ALTER COLUMN TYPE` with bound defaults, `DROP TYPE` dependency
chains, partial indexes, etc.) are *never exercised* by your test suite.

## The Hidden Failure Mode

Long-lived dev/staging databases get migrated **incrementally**, one revision
at a time, as commits land. A migration that contains a structural bug will
appear to work because the previous state already had whatever it expected.

The bomb only detonates when **someone runs `alembic upgrade head` against a
brand-new empty database** — typically a new contributor bootstrapping their
laptop, a CI provisioning a fresh container, or a prod cutover. By then the
person who wrote the migration is no longer paged in to fix it.

## Concrete Bugs This Catches

These are real classes of bugs that pass every SQLite test but break on a
fresh PG:

1. **`ALTER COLUMN TYPE` blocked by an enum-typed `DEFAULT`**
   ```
   DependentObjectsStillExistError: cannot drop type tasksource because other
   objects depend on it
   DETAIL: default value for column source of table tasks depends on type tasksource
   ```
   Cause: column has `DEFAULT 'foo'` typed as the old enum. `ALTER COLUMN TYPE
   VARCHAR` succeeds for the column but the default still references the enum,
   so `DROP TYPE` fails. Fix: `ALTER COLUMN ... DROP DEFAULT` *first*, then
   re-`SET DEFAULT` after the enum is back. SQLite has no enum-bound defaults.

2. **`CREATE TYPE` colliding with SQLAlchemy's metadata-level enum DDL listener**
   ```
   DuplicateObjectError: type "activitylevel" already exists
   ```
   Cause: `op.execute("CREATE TYPE foo")` followed by `op.create_table(...,
   sa.Enum(..., name="foo"))` — even with `create_type=False` on the migration's
   own Enum, the model's metadata-bound listener fires another `CREATE TYPE`
   inside `create_table`. Fix: drop the explicit `op.execute("CREATE TYPE...")`
   and let SQLAlchemy create it once, OR wrap in `DO $$ ... EXCEPTION WHEN
   duplicate_object ...`. SQLite has no enum types.

3. **`DROP TYPE` blocked by surviving FKs / dependent objects** — same family
   as #1 but with foreign keys, default expressions, views, etc.

4. **Partial / functional indexes** that PG accepts but SQLite silently
   ignores or rewrites.

## The Smoke Test

The pattern: pytest test that spins up a throwaway postgres container via
`docker run -d --rm`, waits for `pg_isready`, runs `alembic upgrade head` once,
asserts exit 0, tears down. **No new dependencies**, just `subprocess` +
the existing `docker` binary. Skips automatically when docker is unavailable
so it does not break local laptops without docker.

```python
# backend/tests/test_alembic_fresh_migration.py
"""Smoke test: alembic upgrade head must succeed against a fresh PostgreSQL."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
import uuid

import pytest


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        subprocess.run(["docker", "info"], check=True, capture_output=True, timeout=5)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return False
    return True


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_pg(container: str, timeout_s: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["docker", "exec", container, "pg_isready", "-U", "myuser", "-d", "mydb"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return
        time.sleep(0.5)
    raise TimeoutError("postgres did not become ready in time")


pytestmark = pytest.mark.skipif(
    not _docker_available(),
    reason="docker is not available; skipping fresh-migration smoke test",
)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ALEMBIC_INI = os.path.join(REPO_ROOT, "backend", "alembic.ini")


def _alembic(database_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    return subprocess.run(
        ["uv", "run", "--project", "backend", "alembic", "-c", ALEMBIC_INI, *args],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=300,
    )


def test_alembic_upgrade_head_on_fresh_postgres() -> None:
    container = f"app-migrate-test-{uuid.uuid4().hex[:8]}"
    port = _free_port()

    subprocess.run(
        [
            "docker", "run", "-d", "--rm",
            "--name", container,
            "-e", "POSTGRES_DB=mydb",
            "-e", "POSTGRES_USER=myuser",
            "-e", "POSTGRES_PASSWORD=mypass",
            "-p", f"127.0.0.1:{port}:5432",
            "postgres:16-alpine",
        ],
        check=True, capture_output=True,
    )
    try:
        _wait_for_pg(container)
        url = f"postgresql+asyncpg://myuser:mypass@127.0.0.1:{port}/mydb"
        result = _alembic(url, "upgrade", "head")
        assert result.returncode == 0, (
            f"upgrade head failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    finally:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True)
```

Runtime: ~2-10 seconds when the postgres image is cached locally. ~30 seconds
on a cold CI image pull.

## Why Not Round-Trip (`upgrade head -> downgrade base -> upgrade head`)?

Round-trip is stronger but breaks intentionally-lossy migrations (e.g.
collapsing a 6-state enum to 4 states cannot be reversed without data loss
and is correctly written to `raise NotImplementedError` on downgrade). For
those projects, the upgrade-only smoke is the right granularity. Round-trip
is appropriate when downgrades are required to be reversible (e.g.
deploy-rollback policy).

## Why Not testcontainers / pytest-docker?

Both work, but they add a dependency for what is one self-contained test.
Plain `subprocess + docker` keeps the test in the same toolchain you already
have and removes any version-pin headache. Switch to testcontainers only if
you need it for several tests.

## CI Wiring

GitHub Actions and most CI services already have `docker` on the runner — the
test runs as-is. If your CI uses a postgres *service container* instead, point
`DATABASE_URL` at the service and **delete the container-spinup code** (just
keep the alembic call). Either shape catches the same bugs.

## Why This Skill Exists

I had a Plan view overhaul branch with ~30 alembic revisions. Backend tests
were 80%+ green on SQLite. e2e mock tests were 89/89 green. e2e *live* tests
ran against a long-lived dev postgres that had been migrated commit-by-commit
for weeks. **Two PG-only migration bugs** (DROP DEFAULT trap on the
TaskSource enum, CREATE TYPE collision on `activitylevel`) sat undetected
the entire time and only surfaced when I tried to run the backend on a fresh
laptop postgres. The fix was three lines per bug; the time wasted finding
them was hours. A 10-second smoke test would have failed at PR time.

The unit-test-vs-deploy-DB engine mismatch is the real root cause; this skill
is the cheapest way to close the gap without giving up SQLite's speed for the
rest of the suite.
