---
name: pytest-coverage-gotchas
description: "pytest-cov Coverage Gotchas — diagnosing false coverage failures and async 0% coverage"
version: 1.0.0
---

# pytest-cov Coverage Gotchas

**When to use**: Diagnosing why `--cov-fail-under=80` fails even when the report shows "80%", or why certain async code shows 0% despite tests running.

---

## Gotcha 1: `--cov-fail-under=80` Uses Exact Decimal, Not Rounded Display

**Problem**: The coverage report displays a rounded integer (e.g., `80%`), but `--cov-fail-under=80` compares the **exact fractional total**. Coverage of `79.62%` rounds to `80%` in the display but **fails** the threshold check.

```
TOTAL   4097  819  80%                ← displayed as 80%
FAIL Required test coverage of 80% not reached. Total coverage: 79.62%
                                       ← actual fractional: 79.62%
```

**Symptom**: Test run reports "80%" in the table but then immediately prints `FAIL Required test coverage of 80% not reached. Total coverage: 79.XX%`.

**Fix**: You need the exact decimal ≥ 80.00%. Adding just 1-2 covered lines may not be enough if the gap is fractional. Use `--cov-report=term-missing` to see exactly which lines are uncovered and target them precisely:

```bash
uv run pytest backend/tests/ -q --tb=no \
  --cov=backend/src \
  --cov-report=term-missing \
  --cov-fail-under=80 2>&1 | grep -E "TOTAL|FAIL|80%"
```

**Mental model**: Think of `--cov-fail-under=80` as `>= 80.000...` not `display_rounded >= 80`.

---

## Gotcha 2: ASGI Transport Doesn't Track Async Endpoint Bodies

**Problem**: When testing FastAPI endpoints through `httpx.AsyncClient` (ASGI transport), `pytest-cov` does **not** instrument the async function bodies of route handlers. The endpoint gets called and returns the right response, but the function body lines show as uncovered.

```python
# tasks.py
@router.get("/{task_id}")
async def get_task(task_id: uuid.UUID, db=Depends(get_db)):  # ← line covered
    repo = TaskRepository(db)                                 # ← NOT covered
    task = await repo.get_by_id(task_id)                    # ← NOT covered
    if task is None:                                         # ← NOT covered
        raise HTTPException(404)
    return build_task_response(task)                         # ← NOT covered
```

Even with an HTTP test that calls `GET /tasks/{id}` and asserts `200 OK`, coverage for the handler body will be 0%.

**Why**: pytest-cov uses `sys.settrace()`. ASGI dispatch runs the async handler in a way that bypasses the trace hook for the inner function body.

**Workarounds**:
1. **Unit-test business logic directly** — test the helper functions (`build_task_response`, `validate_dependencies_exist`) without going through HTTP
2. **Test service/repository layer** — HTTP tests verify integration, unit tests drive coverage
3. **Accept the gap** — API route handlers are thin glue; keep logic in services/repositories where coverage works

**Do NOT**: Write dozens of HTTP tests expecting them to raise coverage of route handler files — they won't.

---

## Gotcha 3: Coverage of Files Not Imported During Tests

**Problem**: If a source file is never imported during the test run, `pytest-cov` may show it as 0% or not at all. This can silently drag down totals.

**Fix**: Ensure your `--cov=backend/src` argument covers the root package so that all modules are tracked (even if not imported). You can also add `--cov-report=term-missing` to spot files with unexpectedly low coverage.

---

## Quick Reference

```bash
# See exact per-file missing lines
uv run pytest backend/tests/ --cov=backend/src --cov-report=term-missing -q

# Check exact fractional total (not rounded)
uv run pytest backend/tests/ --cov=backend/src --cov-fail-under=80 -q 2>&1 | tail -5

# Find which files are dragging coverage down
uv run pytest backend/tests/ --cov=backend/src --cov-report=term-missing -q 2>&1 \
  | awk '$NF < 80 && NF > 3'
```
