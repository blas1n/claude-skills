---
name: bsvibe-llm-wrapper-not-raw-litellm
description: When a BSVibe product needs LLM access — BSGateway-routed or direct opt-out — wrap `bsvibe_llm.LlmClient`, never import litellm directly. And when you have two dispatch paths (or anticipate a third), define one Protocol so callers depend on the interface, not a Union of concretes.
trigger: when designing/implementing per-tenant LLM dispatch in any BSVibe product (BSGateway, BSNexus, BSage, BSupervisor) — especially when adding a second executor kind or a direct-vendor opt-out
category: pattern
---

# bsvibe-llm wrapper over raw litellm, Protocol over Union

Two lessons from BSNexus G6.2 (2026-05-11). Initial implementation passed tests and lint but was wrong on two axes that only show up in review.

## Lesson 1 — Use `bsvibe_llm.LlmClient`, not raw litellm

CLAUDE.md says "use litellm only inside `core/llm/`; everywhere else goes through BSGatewayClient." That wording is **load-bearing on the word "inside"** — it does NOT mean "inside `core/llm/` you may import litellm directly." The shared package `bsvibe_llm` already wraps litellm with:

- **`RunAuditMetadata`** — typed wire contract every BSVibe product agrees on. BSGateway rejects anonymous traffic; raw `litellm.acompletion(..., metadata=dict)` will drift the dict shape and you'll find out at the BSGateway audit hop.
- **Retry + fallback chain** — `RetryPolicy` + `FallbackChain` per provider. Reimplementing this in the product means each product reinvents retry behavior.
- **Reasoning suppression** — strategy per provider (Anthropic extended thinking, OpenAI o-series, Ollama reasoning, mlx-lm bypass). Raw litellm gives you naked reasoning output for compile-time call sites that want short structured replies.
- **Cost / audit-metadata flattening** — `metadata.to_metadata()` builds the dict BSGateway parses on `async_pre_call_hook`. Hand-rolling this is the most common drift point.

### Decision tree

When you reach for an LLM in a BSVibe product:

1. **Default**: `bsvibe_llm.LlmClient(...).complete(messages=..., metadata=RunAuditMetadata(...), direct=False)` — routes through BSGateway.
2. **Direct opt-out** (per-tenant self-host endpoint, the routing hook itself, anything that must not recurse through BSGateway): same `LlmClient` with `direct=True`. The `api_base` / `api_key` come from `LlmSettings` constructor args.
3. **Never**: `from litellm import acompletion`. There is no good reason inside a product.

### Enforcement

In each product's test suite, drop a positive-grep guard:

```python
def test_litellm_is_not_imported_directly_by_<product>():
    """litellm is only a transitive dep via bsvibe-llm. Direct imports
    bypass the shared retry / fallback / audit-metadata layer."""
    repo = Path.cwd()
    src_root = repo / "src"
    violations = [
        f"{p.relative_to(repo)}: {imported}"
        for p in src_root.rglob("*.py")
        for imported in _imports_for(p)
        if imported == "litellm" or imported.startswith("litellm.")
    ]
    assert violations == [], (
        "Use bsvibe_llm.LlmClient instead. Leaks: " + str(violations)
    )
```

Drop the direct `litellm>=…` pin from `pyproject.toml` so `uv sync` doesn't keep it alive after you remove the imports — `bsvibe-llm` carries it transitively.

## Lesson 2 — Protocol over Union when N ≥ 2 implementations

Two-path LLM dispatch in BSNexus = `BSGatewayClient` and `DirectLLMAdapter` today, possibly more kinds later (managed vault path, no-LLM mock for demos, …). Initial resolver:

```python
async def resolve_executor(...) -> BSGatewayClient | DirectLLMAdapter | None: ...
```

Works fine for two. Falls apart on the third — every caller that branched `if isinstance(client, BSGatewayClient)` or used the Union type needs to grow.

### Pattern

Define a Protocol once. Make every concrete client structurally conform. Return the Protocol type.

```python
# core/executor_config/protocol.py
from typing import Protocol, runtime_checkable

@runtime_checkable
class ExecutorClient(Protocol):
    async def execute(
        self,
        *,
        messages: list[dict[str, Any]],
        metadata: dict[str, Any],
        model: str,
        workspace_dir: str | None = None,
        mcp_servers: dict[str, Any] | None = None,
        on_chunk: Callable[[str], Awaitable[None]] | None = None,
    ) -> dict[str, Any]: ...

# resolver
async def resolve_executor(...) -> ExecutorClient | None: ...
```

Both clients duck-type into `ExecutorClient` because they expose the same `execute()` shape. Add a third kind = new class + new `resolver` branch. **No call site changes.**

### When this matters

Apply Protocol-over-Union when:

- You have ≥ 2 implementations of the same operation.
- You expect future kinds (the kind enum has room, the user mentioned extensibility, you're behind a config table).
- Callers don't actually need the concrete type — they just call `client.execute(...)`.

Don't apply when:

- One implementation, no future kinds planned. Pre-mature abstraction.
- The two implementations diverge significantly in shape (e.g., one is async, the other is not — then they're not the same operation).

### Conformance test

Lock both concrete classes against the Protocol so a future refactor doesn't silently break duck-typing:

```python
def test_bsgateway_client_conforms_to_executor_client_protocol():
    client = BSGatewayClient(base_url="https://gateway.bsvibe.dev", api_key="x")
    assert isinstance(client, ExecutorClient)

def test_direct_adapter_conforms_to_executor_client_protocol():
    adapter = DirectLLMAdapter(base_url=None, api_key="sk-x", client=stub)
    assert isinstance(adapter, ExecutorClient)
```

`@runtime_checkable` Protocols give you `isinstance()` for free.

## Why both lessons together

They co-occur because the BSGateway-vs-direct dispatch is exactly where:

1. The temptation to import litellm is highest (you "just need" one async call).
2. The two-path Union pattern feels natural at first (you literally have two paths).

Catching both before merge means the wire contract stays unified across products *and* the codebase doesn't pay churn tax when the third executor kind lands.

## References

- CLAUDE.md MUST rule "Two-path LLM dispatch" (Phase 2b, 2026-05-04).
- `bsvibe-python/packages/bsvibe-llm/` (the wrapper this skill points at).
- BSNexus G6.2 PR — initial commit imported litellm + returned Union; revision commit migrated to bsvibe_llm + Protocol after review.
