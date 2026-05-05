---
name: bulk-batch-partial-write-discard
description: Batch processing functions that wrap the WHOLE chunks loop in try/except discard their on-disk partial work in the returned result when any single chunk fails. Symptom — caller logs "0 written" while filesystem actually has N notes. Detection requires real-data e2e + intentional mid-batch failure; single-chunk unit tests miss it.
---

# Bulk-batch try/except scope buries partial work

## The trap

A batch processing function loops over chunks, each chunk does side-effect-y
work (writes files, mutates a DB, calls external services with non-idempotent
effects). The naive shape is:

```python
async def compile_batch(items, ...):
    chunks = _chunk_batch(items, budget)
    notes_created = 0
    actions = []
    try:
        for chunk in chunks:
            plan = await self._plan(chunk)            # LLM call
            result = await self._execute_plan(plan)   # writes garden notes
            actions.extend(result.actions)
            notes_created += result.notes_created
    except Exception:
        logger.warning("compile_batch_failed", exc_info=True)
        return _empty_result()                        # ← DROPS the running totals
    return CompileResult(notes_created=notes_created, actions_taken=actions, ...)
```

If chunk N succeeds and chunk N+1 raises (LLM timeout, malformed JSON, oom),
the writes from chunks 1..N are already on disk, but the caller sees
`notes_created=0` and `actions_taken=[]`. Plugins / CLIs / dashboards that
trust the returned counts misreport "import failed" while the user's vault
silently has half-finished state.

The bug is silent because:
- The on-disk side effects from earlier chunks are real and persistent.
- The reported counts say nothing happened.
- Logs look like the whole call failed, even though most of it succeeded.

## Why unit tests miss it

Common batch-test fixtures fall into one of two shapes:

1. **Single-chunk happy-path** — one mock LLM response, one chunk, no
   failure injection. The try/except never trips.
2. **Multi-chunk happy-path** — same mock returned for every chunk, all
   succeed. Verifies chunking exists but not partial failure.

Neither shape exercises the **"first chunk succeeds, later chunk raises"**
path that production hits the moment any LLM is non-deterministically slow,
any JSON arrives malformed, or any retry budget exhausts.

The 27-unit-test suite for BSage's `IngestCompiler.compile_batch` covered
both happy-path shapes and STILL missed this. The bug surfaced only when a
real ollama qwen3:14b run timed out mid-batch on a 32-file import: 2 garden
notes on disk, returned `notes_created=0`.

## The fix pattern

Move the try/except inside the chunks loop. Per-chunk failure logs and
continues, never aborts the whole batch. Track failures separately so
callers / observability still know something went wrong.

```python
chunk_failures = 0
for chunk in chunks:
    try:
        plan = await self._plan(chunk)
        result = await self._execute_plan(plan)
    except Exception:
        chunk_failures += 1
        logger.warning("compile_batch_chunk_failed", exc_info=True)
        continue
    actions.extend(result.actions)
    notes_created += result.notes_created
return CompileResult(
    notes_created=notes_created,
    actions_taken=actions,
    chunk_failures=chunk_failures,   # ← surfaces partial state
    ...
)
```

Two non-obvious requirements:

- The result type needs a `chunk_failures` (or equivalent) field so callers
  can distinguish "all 5 chunks ok" from "3 ok / 2 dropped". A bare counter
  is enough; you don't need the exception payloads bubbled up.
- The log line per failed chunk should carry enough context (`chunk_size`,
  `seed_source`) to be triageable from logs alone — re-running the whole
  batch to reproduce one chunk's failure is rarely cheap.

## Regression test pattern

The unit test that catches this needs **two distinct mock responses**:
one that succeeds, one that raises. Force chunking by sizing inputs above
half the budget so two chunks form deterministically.

```python
async def test_partial_chunk_failure_preserves_earlier_results(
    self, vault_and_writer, mock_llm
):
    good_plan = json.dumps([{...one create action...}])
    mock_llm.chat = AsyncMock(side_effect=[good_plan, RuntimeError("LLM down")])
    compiler = self._make_compiler(writer, mock_llm, batch_char_budget=4_000)

    big = "x" * 3_000   # each item > half the budget → 2 chunks
    items = [BatchItem(label="a.md", content=big),
             BatchItem(label="b.md", content=big)]
    result = await compiler.compile_batch(items=items, seed_source="partial")

    assert mock_llm.chat.await_count == 2
    assert result.notes_created == 1                 # first chunk's write survives
    assert len(result.actions_taken) == 1
    assert result.llm_calls == 1
```

`AsyncMock(side_effect=[ok_response, exc])` is the key — `side_effect` as a
list dispatches a different response per call. `return_value` always returns
the same one and won't reproduce the bug.

## Where this generalises

The pattern recurs in any pipeline that:

- iterates over chunks/batches/pages/files
- has side effects per chunk that persist outside the function (filesystem,
  database row, queue publish, paid API call)
- returns aggregate counts to a caller that uses them for status reporting

Audit candidates with grep:

```bash
grep -rn "for .* in chunks\|for .* in batches\|for .* in pages" \
     | xargs grep -l "try:" | xargs grep -l "except"
```

Anywhere the body of the for-loop is INSIDE a try block at function scope,
not the inner statement, you have this trap.

## Detection in code review

When reading a batch processor:

1. Find the chunk loop.
2. Find the nearest enclosing `try`. If it's outside the loop, partial-write
   discard is possible. If it's inside the loop body, you're safe.
3. Look at the result type. If there's no `chunk_failures` / `partial` /
   `errors` field, the caller has no way to tell partial succeeded from
   total failure. Both bugs travel together.

## Real-world anchor

BSage's `IngestCompiler.compile_batch` ([bsage/garden/ingest_compiler.py](https://github.com/BSVibe/BSage)) —
fixed in commit 11e7f6e2 of feat/dynamic-ontology. Bug pre-dated the
dynamic-ontology refactor but the bigger batches the refactor encourages
(no per-note classification cost, so batches of 30+ notes are routine)
made it a daily occurrence rather than a rare edge case.
