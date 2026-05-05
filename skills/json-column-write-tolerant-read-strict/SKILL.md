---
name: json-column-write-tolerant-read-strict
description: SQLAlchemy JSON / JSONB columns accept any JSON-serializable value on write. The Pydantic response_model on the GET endpoint is strict. A row written as a bare string sits in the DB happily until a fetch hits ResponseValidationError → 500. Producer tests + response-schema tests that don't round-trip via the API miss this.
version: 1.0.0
task_types: [debugging, testing]
category: trap
---

# JSON column write-tolerant, response_model read-strict

## Symptom

```
fastapi.exceptions.ResponseValidationError: 463 validation errors:
  File "/app/backend/src/api/inside.py", line 33, in list_runs
    GET /api/v1/requests/{request_id}/runs
```

`GET` endpoint 500s. The row exists, the field is set, the producer
doesn't crash, **the producer's unit tests are green**. The breakage
only shows up when something fetches the row through the response
schema.

## What's actually wrong

Two layers disagree on the shape of a JSON-backed field:

```python
# models/execution_run.py
output_ref: Mapped[dict | None] = mapped_column(JSON, nullable=True)

# schemas/founder.py
class ExecutionRunResponse(BaseModel):
    output_ref: dict[str, Any] | None      # ← strict dict|None

# core/llm/direct_client.py
return {"output_ref": "".join(aggregated_text)}   # ← bare string
```

The model's type hint (`Mapped[dict | None]`) is **a comment, not a
constraint**. SQLAlchemy hands the value straight to PostgreSQL's JSON
encoder, which happily accepts any JSON-serializable payload — string,
list, number, dict. The DB takes a string. The next `SELECT` returns
that string. Pydantic's response model rejects it. 500.

The asymmetry: **writes are tolerant** (anything serializable goes
in), **reads are strict** (response_model enforces the schema). Add
in JSON columns being free-form by design and you get a class of bugs
where the producer succeeds, the row exists, and only the read path
detects the mismatch — at runtime, in production.

## How tests miss it

The structural blindspot has three components, all of which were
present in the case that motivated this skill:

1. **Producer unit tests** patch `acompletion` (or whatever the
   downstream is) and assert the *intermediate result dict shape*:
   ```python
   assert result == {"output_ref": "Done", ...}   # passes
   ```
   They don't write the row and read it back through the API.

2. **Response model tests** assert that `ExecutionRunResponse(**row)`
   parses correctly when the row is hand-shaped to match — i.e.
   they only see well-formed inputs. They don't probe what happens
   when the row was written by a producer with a different shape.

3. **Schema-level integration tests** mock the executor (it returns
   a dict-shaped fixture) and assert the API surface. The real
   producer's wire format never enters the test pipeline.

All three layers can be 100% green while production 500s on the first
real run that exercises the producer.

## Diagnostic recipe

When `GET` returns 500 and the row exists:

```bash
# 1. What's actually in the DB?
docker exec <pg> psql -U <user> -d <db> -c "
SELECT jsonb_typeof(<col>::jsonb) AS shape, count(*)
FROM <table>
GROUP BY shape;
"
# Expected for a 'dict | None' field: only 'object' and NULL.
# If you see 'string' / 'array' / 'number' rows, the producer's
# write path doesn't match the response schema.
```

If a non-object shape exists for a `dict|None` field → the producer
wrote it. Find every writer of that column.

## Fix pattern

**Pick a canonical wrapper convention** — usually `{"inline": text}`
for inline-text payloads, `{"ref": "<storage-path>"}` for blob
references, `{"items": [...]}` for arrays-of-things — and enforce it
at every writer. The wrapper is the contract; the schema enforces it.

```python
# Canonical wrapper convention for output_ref
return {
    "output_ref": {"inline": text},   # not the bare ``text``
    ...
}
```

In our case `BSGatewayAdapter` already wrapped via
`result["output_ref"] = {"inline": partial}`; the new
`DirectLLMAdapter` was the outlier. Once you spot the divergence,
the fix is one line.

## Defenses (rank-ordered)

1. **A round-trip integration test** — the cheapest, highest-yield
   defense. Producer writes through the real path → API GETs through
   the real response_model. Catches *any* shape divergence between
   writers and the schema.

   ```python
   async def test_run_output_ref_roundtrip(client):
       # Real executor, real DB, real route. No mocks of the producer.
       r = await dispatch_real_run(...)
       resp = await client.get(f"/api/v1/requests/{r.request_id}/runs")
       assert resp.status_code == 200      # ← the bug would 500 here
   ```

2. **Tighten the column type** — `JSON` → custom typed column or a
   pre-write validator. SQLAlchemy's type hint isn't enforced; add a
   `@validates("output_ref")` or a custom `TypeDecorator` that
   raises if the input isn't a dict (matching the response_model).
   Caps the bug at write time instead of read time.

3. **Pre-commit grep** for known-canonical writer paths. If your
   convention is `{"inline": ...}`, a CI check that fails on
   `output_ref": "<not a brace>"` patterns in source catches drift
   before merge. Brittle but cheap.

4. **Migration safety net** for existing bad rows. After fixing the
   writer, the rows already in production are still broken. One-shot
   SQL converts them in place:
   ```sql
   UPDATE <table>
   SET <col> = jsonb_build_object('inline', <col>::jsonb #>> '{}')
   WHERE jsonb_typeof(<col>::jsonb) = 'string';
   ```
   `#>> '{}'` extracts the bare string value (without the JSON
   quotes). Runs against the live DB; not promoted to alembic
   unless a column rename or schema change accompanies.

## Related, non-overlapping skills

- `e2e-mock-shape-drift` — mock fixtures using wrong API response
  shape; passes silently because the frontend handles malformed
  data. Different layer (frontend tolerant), same root pattern
  (write/read asymmetry across a boundary).
- `mock-fixtures-hide-wiring-bugs` — dependency_overrides + pre-seeded
  fixtures hide whether glue is wired. Same blindspot family
  (real-backend integration tests are the missing layer in both).

If you're touching a JSON-backed field in a Pydantic/SQLAlchemy
stack, search for both of those plus this skill before assuming
your producer + response tests have you covered.
