---
name: ollama-litellm-streaming-tool-call-traps
description: Two reproducible traps when running Ollama via LiteLLM in streaming mode with multi-turn tool calls — concatenated arguments under the same streaming index, and OOM mid-stream masquerading as "generator didn't stop after athrow()" cleanup error.
version: 1.0.0
task_types: [coding, debugging]
category: trap
---

# Ollama + LiteLLM streaming tool-calls: two traps you only see live

These two failures don't appear in unit tests, integration tests with mock
backends, or single-turn probes. They surface only when streaming + multi-turn
+ a real Ollama backend are all combined — i.e. live e2e dogfooding. Both
caused real run-blocking regressions on BSNexus 2026-05-08 and took hours
to diagnose because the visible exception is downstream of the actual
cause.

This skill assumes the basics from `litellm-tool-call-provider-probe`
(always use `ollama_chat/`, never `ollama/`) and `ollama-litellm-config`.

---

## Trap 1: concatenated tool_call arguments under the same streaming index

### Symptom

Run starts cleanly. Round 1 tool calls dispatch fine and return results.
On round 2, litellm raises before yielding any chunk:

```
litellm.llms.ollama.chat.transformation.OllamaError: JSONDecodeError: Extra data
  raised inside transform_request when the round-2 messages are sent back
```

The `messages` list looks fine when logged. The actual culprit is round 1's
*assistant* message: its `tool_calls[].function.arguments` string is now
`{"path": "a"}{"path": "b"}` — two JSON objects back-to-back — because
the OLLAMA streaming response emitted **multiple distinct tool_calls under the
same `index`**, and your per-index accumulator concatenated them.

The OpenAI streaming convention is: each distinct tool_call gets its own
`index`. Ollama's chat endpoint violates that for at least
`qwen3-coder:30b` — when the model wants to call `file_write` twice in a
single response chunk, both arrive with the same index.

### Reproduce

Send a system prompt that asks for two `file_write` calls in a single
turn (e.g. "create both `add.py` and `tests/test_add.py` in this round").
Pre-fix, the run transitions to `blocked` on round 2 with the
`JSONDecodeError: Extra data` traceback.

### Fix

Defensive splitter that runs *after* the per-index accumulator and
*before* tool_calls are persisted/sent back. Use
`json.JSONDecoder().raw_decode()` to walk the buffer, emit one
tool_call per parsed object, suffix follow-on call ids so the next
round's `tool_message` addresses the right call:

```python
def _split_concatenated_tool_call_arguments(tool_calls):
    if not tool_calls:
        return tool_calls
    decoder = json.JSONDecoder()
    expanded = []
    for tc in tool_calls:
        args = tc.get("function", {}).get("arguments") or ""
        if not args:
            expanded.append(tc); continue
        try:
            json.loads(args)
            expanded.append(tc); continue   # already clean
        except json.JSONDecodeError:
            pass
        cursor, seq = 0, 0
        while cursor < len(args):
            while cursor < len(args) and args[cursor].isspace():
                cursor += 1
            if cursor >= len(args): break
            try:
                obj, end = decoder.raw_decode(args, cursor)
            except json.JSONDecodeError:
                break  # drop unparseable tail; keep what we recovered
            sub = dict(tc); sub["function"] = dict(tc["function"])
            sub["function"]["arguments"] = json.dumps(obj)
            if seq > 0 and tc.get("id"):
                sub["id"] = f"{tc['id']}-{seq}"
            expanded.append(sub)
            cursor = end; seq += 1
    return expanded
```

Pin with unit tests for: clean passthrough, empty arguments, two-object
split, three-object whitespace-separated split, heterogeneous list,
unparseable remainder dropped, empty list passthrough.

### Why mocks miss it

Per-index accumulators are usually unit-tested with pre-segmented
streaming chunks (one tool_call per index). The bug only appears when
the *real* backend collapses multiple distinct tool_calls into the same
index slot, which mock fixtures don't reproduce because the mock author
already knows the OpenAI convention.

---

## Trap 2: Ollama Metal OOM mid-stream surfaces as `RuntimeError: generator didn't stop after athrow()`

### Symptom

A long-running multi-turn run (10+ rounds) suddenly transitions to
`blocked` with reason `generator didn't stop after athrow()`. The
traceback points to `contextlib.py` at the `__aexit__` of an `async
with` over an MCP session or similar context manager — *not* to any
LLM call. Looks like a `_mcp_session()` cleanup bug.

### Real cause

Buried inside the ExceptionGroup is the actual error:

```
litellm.exceptions.APIConnectionError: litellm.APIConnectionError:
  Ollama_chatException - KeyError: 'message',
  Got unexpected response from Ollama: {'error': 'an error was encountered while running the model:
    error:command buffer 0 failed with status 5
    error: Insufficient Memory (00000008:kIOGPUCommandBufferCallbackErrorOutOfMemory)
    ggml-metal-context.m:235: fatal error'}
```

i.e. the Ollama server (Mac/Metal) ran out of GPU memory mid-generation
and returned an `{"error": ...}` chunk in its NDJSON stream. litellm's
`ollama/chat/transformation.py:chunk_parser` does
`chunk["message"].get("tool_calls")` — KeyError because the OOM chunk
has no `message` key. That KeyError propagates up through the LLM stream
inside an `async with streamablehttp_client(...) as ...:` block. The
mcp `streamablehttp_client` uses an anyio TaskGroup; when one task
raises, the TaskGroup re-raises a BaseExceptionGroup on its own exit.
Because our `_mcp_session()` is itself an `@asynccontextmanager` that
yielded *during* the inner async-with, contextlib's `athrow` finds the
generator hasn't returned cleanly and converts the chain into the
misleading `RuntimeError: generator didn't stop after athrow()`.

### Debug procedure

When you see `generator didn't stop after athrow()`:

1. **Don't trust the surface message.** It's almost never the real
   cause; it's a contextlib artifact when an inner async-with raises
   while you're yielding through.
2. Search the traceback for `ExceptionGroup:` and walk every nested
   `+---------------- N ----------------` frame. The deepest leaf is
   the actual cause.
3. If the leaf is `KeyError: 'message'` from
   `litellm/llms/ollama/chat/transformation.py:chunk_parser`, the
   model server returned a non-streaming error chunk — typically
   Metal OOM, but also rate-limit / timeout / model-load failure.
   Check the GPU memory on the Ollama host, or pick a smaller model.

### Code-side robustness (separate fix from the OOM itself)

The cleanup-path `RuntimeError` hides the real cause. Wrap
`_mcp_session()`'s body so the inner exception bubbles up untouched:

```python
@asynccontextmanager
async def _mcp_session(...):
    try:
        async with streamablehttp_client(url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session
    except BaseException:
        # Let the original cause propagate; do NOT shadow with the
        # contextlib athrow rewrite.
        raise
```

(The `try/raise` looks vacuous but documents intent and prevents a
future refactor from sticking exception-handling between the inner
`async with` and the outer `yield` boundary, which is what triggers
the contextlib rewrite.)

### Why hardware-only?

This isn't reproducible without a real Ollama backend that actually
runs out of GPU memory. The fix is partly hardware (don't OOM) and
partly code (don't shadow the cause). Document the hardware envelope
of your model on each Ollama host so future runs that approach the
limit don't waste hours chasing the wrong error.

---

## Checklist before declaring an Ollama+LiteLLM streaming tool-loop "done"

- [ ] Provider probe passes single-turn tool-calling
      (`litellm-tool-call-provider-probe`).
- [ ] Multi-turn live e2e ran a 5+ round tool loop end-to-end at
      least once — unit tests will not catch trap 1.
- [ ] Concatenated-arguments splitter implemented and unit-pinned.
- [ ] If you ever see `generator didn't stop after athrow()`, you
      check the ExceptionGroup leaves for the real cause before
      blaming your context-manager.
- [ ] Model OOM envelope on the inference host is known; live-LLM
      timeouts (`DELIVERABLE_TIMEOUT_MS` etc.) are sized to it, not
      to the median round-trip.
