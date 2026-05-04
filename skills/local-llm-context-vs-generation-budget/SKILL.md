---
name: local-llm-context-vs-generation-budget
description: "Local LLMs (ollama, llama.cpp) declare huge context windows (200k+ tokens) but generation time scales with input length. On consumer GPUs, glm-4.7-flash with 16k char input times out at 300s; same model with 5k chars finishes in 50-100s. Cap derived budget for local models — declared context ≠ practical generation budget."
version: 1.0.0
---

# Local LLM: Declared Context ≠ Practical Generation Budget

## When to Use

Any system that derives runtime parameters (chunk size, batch budget, max prompt length) from a model's declared context window AND that model is run locally (ollama, llama.cpp, vllm on consumer GPU).

For hosted frontier models (Anthropic, OpenAI, Google) the declared context IS roughly the practical budget — they have datacenter inference pools optimized for long contexts.

## The Trap

```python
# Looks correct
async def derive_batch_budget(model: str, api_base: str) -> int:
    info = await ollama_show(model, api_base)
    max_tokens = info["model_info"]["glm.context_length"]   # → 202752
    return int(max_tokens * 3.5 * 0.4)                       # → 283,852 chars
```

Then you ship a 17,558 char prompt to glm-4.7-flash on consumer GPU and hit 600s timeout. But the model "supports" 202k tokens. What gives?

## Why It Happens

**Token throughput on consumer GPUs is roughly constant per token, but input parsing + KV cache build also scale with input length.** A 17k char input doesn't just take 17k× generation time — it adds:

1. **Prompt processing** — building the KV cache for the whole input
2. **Generation** — each output token's attention spans the full input
3. **VRAM pressure** — long contexts evict things, hurting throughput

For Anthropic Sonnet on their hardware, all three are mostly hidden by fast hardware + batching. For a single-GPU local model, all three add seconds-per-thousand-chars.

**Empirical (glm-4.7-flash:latest with `think=False` on Apple Silicon M-series):**

| Input chars | Generation time | Outcome |
|---|---|---|
| 5k | 50-100s | OK |
| 8k | 80-130s | OK |
| 16k | 300s+ | timeout |
| 17k | 600s+ | timeout |

Not linear — context VRAM cost compounds.

## The Fix

Cap the derived budget separately for local-class models:

```python
_OLLAMA_BUDGET_CAP = 8_000   # empirical: keeps glm-4.7-flash gen under 2 min

async def derive_batch_char_budget(model: str, api_base: str | None) -> int:
    max_input_tokens = await _probe_max_input_tokens(model, api_base)
    if max_input_tokens is None:
        return _DEFAULT_BATCH_CHAR_BUDGET

    budget = int(max_input_tokens * _CHARS_PER_TOKEN * _BUDGET_SAFETY_FRACTION)
    budget = max(budget, _DEFAULT_BATCH_CHAR_BUDGET)

    # Local ollama models: cap regardless of declared context
    if model.startswith(("ollama/", "ollama_chat/")):
        budget = min(budget, _OLLAMA_BUDGET_CAP)

    return budget
```

Hosted models keep the full derived budget (Sonnet 4 → ~280k chars). Local models cap at 8k.

## Tuning the Cap

The right cap is **GPU-class dependent**. For:

- **M-series Mac (consumer GPU)**: 5-8k chars
- **3090 / 4090 (24GB VRAM)**: 12-16k chars
- **Datacenter A100/H100**: 32k+ chars

The fastest way to find your cap:

```python
import time, httpx
async def find_cap(model: str, api_base: str, target_seconds: int = 60) -> int:
    """Binary search for the largest prompt that finishes under target_seconds."""
    lo, hi = 1_000, 32_000
    while lo < hi - 1_000:
        mid = (lo + hi) // 2
        prompt = "x" * mid + "\n\nReply with: done"
        t0 = time.time()
        async with httpx.AsyncClient(timeout=target_seconds * 2) as c:
            try:
                await c.post(f"{api_base}/api/chat", json={
                    "model": model, "stream": False, "think": False,
                    "messages": [{"role": "user", "content": prompt}],
                    "options": {"num_predict": 50},
                })
                elapsed = time.time() - t0
                if elapsed < target_seconds:
                    lo = mid
                else:
                    hi = mid
            except Exception:
                hi = mid
    return lo
```

Run once per (model, GPU) combo and store the result.

## Why This Matters

Without the cap, a system that "auto-scales batch size to model context" will:

1. Pick a huge batch budget for an ollama model
2. Send a giant prompt
3. Hit timeout
4. Return 0 results
5. User assumes the LLM is broken

The cap is the difference between "import works in 12 minutes" and "import returns 0 garden notes after 10 minutes."

## Related

- `ollama-reasoning-model-think-flag` — without `think=False`, even small prompts blow past these limits
- `litellm-tool-call-provider-probe` — sibling pattern of probing model capabilities at startup
