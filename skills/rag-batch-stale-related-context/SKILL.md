---
name: rag-batch-stale-related-context
description: "Batched RAG compile pipelines that compute related-notes context ONCE outside the chunk loop and reuse it across chunks silently break the update path. Symptom: classification works, but no existing notes ever get updated — because chunks N+ see context that's irrelevant to their content. Fix: compute related context per chunk, with that chunk's seeds as the query."
version: 1.0.0
---

# RAG Batch: Stale Related Context Across Chunks

## When to Use

Any LLM pipeline that:
- Processes a batch of N items in chunks (because of context limits or model speed)
- Fetches "related existing notes" via RAG/vector retriever to give the LLM update context
- Has both **create** and **update** code paths in the executed plan

If your pipeline matches and you're seeing "all creates, zero updates" or "the LLM isn't reusing existing notes", this trap likely applies.

## The Bug Pattern

```python
# WRONG — looks reasonable, fails silently
async def compile_batch(items: list[BatchItem], source: str) -> CompileResult:
    chunks = chunk_by_size(items, BUDGET)

    # ← computed ONCE, before the loop
    related_query = "\n\n".join(item.content[:500] for item in items[:3])
    related_context = await retriever.search(related_query)

    for chunk in chunks:
        plan = await llm_plan_updates(chunk, source, related_context)  # ← reused
        await execute_plan(plan)
```

The first 3 items get their semantic neighborhood fetched. Chunks 4-N see the SAME related-notes blob, which has nothing to do with what THEY contain.

The LLM dutifully sees "Existing Related Notes" but they're unrelated to the current chunk → it can't decide "this is the same as that existing note, update it" → defaults to `create`.

## Why It's Silent

1. **Tests cover the create path well.** "Did we create a note?" passes. "Did we correctly update an existing one?" requires a fixture vault with notes that semantically match the seeds — easy to skip.

2. **No exception is thrown.** The retriever returns SOMETHING, the LLM gets SOMETHING in the prompt. The fact that it's stale doesn't surface anywhere.

3. **Demos look great.** `notes_created: 30` reads as success on first import (no existing notes anyway). Re-import same data: `notes_created: 30, notes_updated: 0` — should be `0/30` after dedup, but the pipeline is structurally incapable of updating.

4. **It only matters at scale.** Single-chunk runs (small inputs) work fine because the single chunk IS items[:3]. The bug emerges as soon as content exceeds one chunk.

## How To Notice In Code Review

Grep for `related` / `existing notes` / `retriever.search` calls and check if they're **inside the chunk loop**:

```bash
grep -nB2 -A8 'retriever\.\(search\|retrieve\)' compiler.py
```

Look for the pattern:

```python
related = retriever.search(...)
for chunk in chunks:
    use(chunk, related)         # ← stale, fails silently
```

vs the fix:

```python
for chunk in chunks:
    related = retriever.search(query_from(chunk))
    use(chunk, related)         # ← fresh per chunk
```

If you see the former, ask: "does the LLM ever update existing notes in this pipeline, or only create?"

## The Fix

Move the retriever call inside the loop, build the query from THIS chunk's items:

```python
async def compile_batch(items: list[BatchItem], source: str) -> CompileResult:
    chunks = chunk_by_size(items, BUDGET)

    for chunk in chunks:
        # Per-chunk: each chunk gets context relevant to ITS own seeds
        chunk_query = "\n\n".join(item.content[:500] for item in chunk)
        related_context = await retriever.search(chunk_query)

        plan = await llm_plan_updates(chunk, source, related_context)
        await execute_plan(plan)
```

Cost: +(N_chunks - 1) retriever calls. Almost always negligible vs. the LLM call cost.

## Detection Test

Add a regression test that locks the pattern in:

```python
@pytest.mark.asyncio
async def test_per_chunk_related_lookup(retriever_mock, llm_mock, writer):
    """Each chunk asks the retriever fresh — not items[:3] shared across all."""
    compiler = IngestCompiler(
        garden_writer=writer,
        llm_client=llm_mock,
        retriever=retriever_mock,
        batch_char_budget=4_000,
    )
    big = "y" * 3_000
    items = [
        BatchItem(label="a.md", content=big),
        BatchItem(label="b.md", content=big),
        BatchItem(label="c.md", content=big),
    ]
    await compiler.compile_batch(items=items, seed_source="test")
    # 3 chunks → 3 retriever lookups (was 1 lookup shared across all chunks).
    assert retriever_mock.search.await_count == 3
```

This test is one line that prevents the bug from sneaking back in during refactors.

## Why This Matters

The whole point of having a retriever in a compile pipeline is to let the LLM see related existing content and AVOID DUPLICATION. If the related context is stale, the LLM cannot do its job — it sees seeds without context and creates duplicates.

Symptoms compound over time:
- Day 1: 30 notes imported, all created. OK.
- Day 7: 30 more notes imported, all created. Now you have duplicates.
- Day 30: 1000 notes, half are conceptual duplicates.
- The user complains: "I thought this would dedupe / merge / link to existing notes."

The bug never raised an error, but the system's value proposition silently degraded.

## Related

- `static-ontology-knowledge-graph-trap` — sister trap: classification works → assume system works, but value isn't there
- `absence-measurement-validity-check` — "X never happens" is suspect when the producer of X may be off / misconfigured
