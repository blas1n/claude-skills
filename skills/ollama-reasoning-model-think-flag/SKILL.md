---
name: ollama-reasoning-model-think-flag
description: "Ollama reasoning models (glm-4.7-flash, qwen3-thinking, etc.) emit hundreds of CoT tokens before the actual response unless `think: false` is sent. litellm does NOT forward this kwarg to ollama — visible in extra_kwargs but dropped on the wire. 600s+ timeouts on otherwise-fast prompts."
version: 1.0.0
category: trap
---

# Ollama Reasoning Model `think=False` Trap

## When to Use

Any system that:
- Calls a reasoning-class ollama model (glm-4.7-flash, qwen3-thinking, deepseek-r1, etc.) **and**
- Goes through litellm (or another abstraction) that doesn't expose ollama-specific kwargs as first-class
- Sees timeouts on prompts that should be fast (5k char prompt → 60s+) or empty `response` strings with `num_predict` caps

If the model has a `thinking` field in its raw API response, this trap applies.

## The Symptom

```python
# litellm call
response = await litellm.acompletion(
    model="ollama_chat/glm-4.7-flash:latest",
    messages=[{"role": "user", "content": "Reply with just OK"}],
    api_base="http://localhost:11434",
    think=False,        # ← passed but litellm drops this on the wire
    timeout=300,
)
# → 9 seconds for "OK" (should be <1s)
# → Larger prompts: 300s+ timeout
```

Direct ollama call works:
```bash
curl http://localhost:11434/api/chat -d '{
  "model": "glm-4.7-flash:latest",
  "messages": [{"role": "user", "content": "OK"}],
  "stream": false,
  "think": false
}'
# → 0.24s
```

## Why It's Silent

1. **litellm forwards extra kwargs to its provider adapter** — for anthropic, openai, etc. they get mapped to provider-specific params. For ollama, `think=False` lands in `extra_kwargs` and is visible in error logs, but the ollama adapter doesn't translate it to the `/api/chat` body.

2. **No error is raised** — the model just thinks for tokens you don't see. `response` may be empty (if `num_predict` exhausts during thinking) or arrive late.

3. **GLM-4.7-flash specifically** has a `thinking` field separate from `response`. By default the model fills thinking with hundreds of tokens of reasoning before producing the actual response. Without `think=False` even "say OK" generates 600+ thinking tokens.

4. **Test prompts are usually short** — and short prompts barely surface the issue (8s instead of 0.5s feels "OK"). Long prompts (10k+ chars) blow up generation time non-linearly because thinking scales with input complexity.

## The Fix

### Option A — Bypass litellm for reasoning models (most reliable)

Wire a small `OllamaThinkAwareLLM` that talks to `/api/chat` directly:

```python
class OllamaThinkAwareLLM:
    """Thin LiteLLMClient-shaped wrapper that honors think=False for ollama."""

    def __init__(self, model: str, api_base: str, *, timeout: float = 300.0) -> None:
        # model is the bare ollama name like "glm-4.7-flash:latest" — no provider prefix
        self.model = model
        self.api_base = api_base
        self._client = httpx.AsyncClient(timeout=timeout)

    async def chat(self, system: str, messages: list[dict], **_) -> str:
        work = [{"role": "system", "content": system}, *messages]
        resp = await self._client.post(
            f"{self.api_base}/api/chat",
            json={
                "model": self.model,
                "messages": work,
                "stream": False,
                "think": False,            # ← the whole point
                "options": {"num_predict": 4096},
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return (data.get("message") or {}).get("content", "")
```

Auto-detect when to swap: if `runtime_config.llm_model` starts with `ollama/` or `ollama_chat/` AND the model name matches a known reasoning prefix (`glm-`, `qwen3-thinking`, `deepseek-r1`, etc.), use the bypass. Otherwise keep litellm.

### Option B — Patch litellm config (fragile)

Some litellm versions accept `extra_body={"think": False}` for ollama. Verify with a probe before relying on it — version-dependent and undocumented.

```python
response = await litellm.acompletion(
    ...,
    extra_body={"think": False},
)
```

If your `extra_kwargs` shows `think: False` but generation time stays high, the kwarg is being dropped. Switch to Option A.

## Detection Probe

Run this 5-line check at startup against your configured model:

```python
async def detect_reasoning_model(model: str, api_base: str) -> bool:
    """True if the model emits a `thinking` field — i.e. needs think=False."""
    bare = model.split("/", 1)[1] if "/" in model else model
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{api_base}/api/chat", json={
            "model": bare,
            "messages": [{"role": "user", "content": "Reply only: OK"}],
            "stream": False,
            "options": {"num_predict": 50},
        })
    msg = r.json().get("message", {})
    return bool(msg.get("thinking"))
```

If True, the model is a reasoner. If `think=False` doesn't reach the model via your current LLM client, swap to direct httpx.

## Cost of Missing This

- Demo / e2e jobs that "should take 30s" timing out at 600s
- Production looking like the LLM is hung when it's actually generating thousands of CoT tokens
- Wasted GPU cycles on hidden reasoning the user never sees
- 17k char prompt: 600s+ with thinking, ~50-100s without
- 5k char prompt: 100s+ with thinking, ~5s without

## Related

- `litellm-tool-call-provider-probe` — sibling trap (litellm drops `tools` for some providers)
- `local-llm-context-vs-generation-budget` — the practical generation budget for local LLMs is much smaller than declared context
