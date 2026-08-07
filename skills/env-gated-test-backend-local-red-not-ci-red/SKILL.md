---
name: env-gated-test-backend-local-red-not-ci-red
description: When a test harness picks its DB backend from an env var (`use_real_pg()` → Postgres when `BSVIBE_DATABASE_URL` is set, else in-memory SQLite), a locally-red suite is NOT evidence that main is broken — CI sets the var and runs green. Reproduce under CI's env before reporting breakage, and fix the production code that assumed one backend's semantics.
category: trap
---

# Env-gated test backend: local red ≠ CI red

## Problem

Mature repos pick the test database at runtime:

```python
def use_real_pg() -> bool:
    """True when BSVIBE_DATABASE_URL is set AND that Postgres is reachable."""
    return bool(os.environ.get("BSVIBE_DATABASE_URL")) and can_reach_pg()

url = pg_url() if use_real_pg() else "sqlite+aiosqlite:///:memory:"
```

CI sets the var (a `services: postgres:` container). A fresh local checkout does
not. So the same commit gives two different suites, and a fresh clone can show a
block of failures that CI has never seen.

The wrong move is to report "main is red" and reorder the work around it. That
misstates the state of the repo to whoever is reading, and can send you fixing
something that was never broken in production.

The right move is *also* not "ignore it" — the failures usually mark real
fragility, just not an outage.

### The shape it takes with datetimes

The most common instance: Postgres `TIMESTAMPTZ` round-trips **aware**, SQLite
round-trips **naive**. Production code that subtracts a stored value from
`datetime.now(UTC)` works forever on PG and raises on SQLite:

```python
dispatched_at = snap.conflict_dispatched_at          # naive on SQLite
elapsed = (now - dispatched_at).total_seconds()      # TypeError there, fine on PG
# TypeError: can't compare offset-naive and offset-aware datetimes
```

Downstream, the exception is swallowed or reroutes a state machine, so the
visible failures are *status assertions* several layers away from the cause —
`assert NEEDS_RESOLUTION is FAILED`, `assert 0 == 1` — which hide the real one.

## Solution

### 1. Reproduce under CI's environment before reporting

Read the workflow to learn what CI actually sets, then mirror it:

```bash
grep -n -iE "services:|DATABASE_URL|postgres" .github/workflows/ci.yml
docker port <pg-container>          # find the local port

BSVIBE_DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5442/db" \
  uv run --extra dev pytest <failing_test_file> -q
```

Green there ⇒ CI is green ⇒ **main is not red**; say so plainly and correct any
earlier claim.

### 2. Find the real cause before deciding test vs production

Run one failing test with a full traceback and look for a frame in `backend/`:

```bash
uv run --extra dev pytest <test>::<case> -q --tb=short -p no:logging \
  | grep -E "backend/|TypeError"
```

- Frame lands in **production code** → production is backend-fragile. Fix it.
- Frame lands only in the **test** (asserting a row value against an aware
  constant) → the assertion is over-specified. Fix the test.

Both happened in one suite here; don't assume it's all one or all the other.

### 3. Normalise at the boundary, not at each comparison

For the production half, convert once where rows enter the domain — every
downstream comparison is then safe and future ones can't regress:

```python
def _aware(dt: datetime) -> datetime:
    """Postgres round-trips aware, SQLite does not; restore UTC before comparing."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)

@classmethod
def of(cls, row: Row) -> Snapshot:
    return cls(
        deadline_at=_aware(row.deadline_at),
        conflict_dispatched_at=(
            _aware(row.conflict_dispatched_at) if row.conflict_dispatched_at else None
        ),
        ...
    )
```

For the test half, compare instants rather than tz representations:

```python
def _at(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)

assert _at(fetched.next_poll_at) > _FIXED_NOW
```

### 4. Verify both backends

A fix that makes SQLite pass must not regress PG:

```bash
uv run --extra dev pytest <file> -q                                   # SQLite
BSVIBE_DATABASE_URL=... uv run --extra dev pytest <file> -q           # Postgres
```

## Corollary

The gate cuts the other way too: a local SQLite-only run **cannot** see
PG-only defects (enum DDL, `SKIP LOCKED`, RLS, `NOT NULL` on a real column).
When your change touches schema or locking, run the PG path locally — don't let
CI be the first execution.

## Related

- `sqlite-naive-datetime-system-tz-silent-shift` — the silent-wrong-answer sibling of this TypeError
- `sqlalchemy-sqlite-pg-compat`
- `alembic-fresh-pg-smoke-test`
