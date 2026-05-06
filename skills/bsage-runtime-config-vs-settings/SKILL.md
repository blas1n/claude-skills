---
name: bsage-runtime-config-vs-settings
description: When adding a configurable knob to BSage, decide between Settings (env-loaded, immutable per-process) vs RuntimeConfig (mutable, persisted, user-editable via SettingsView). Choosing wrong means env vars only — users can't tune it without redeploy.
---

# BSage: RuntimeConfig vs Settings — picking the right config layer

## Trigger

You are about to add a new config field to BSage (LLM model, API base, threshold, feature flag, etc.) and you find yourself reading `settings.foo` from `bsage.core.config.Settings` somewhere downstream.

**Stop.** Decide first whether this should live on `RuntimeConfig` instead.

## The two layers

BSage has two configuration layers that look similar but serve different purposes:

| Layer | File | Source | Mutable at runtime? | Where set |
|---|---|---|---|---|
| `Settings` | `bsage/core/config.py` | `.env` / env vars (pydantic-settings) | No (immutable per process) | Operator at deploy time |
| `RuntimeConfig` | `bsage/core/runtime_config.py` | JSON file at `settings.credentials_dir/runtime_config.json`, seeded from `Settings` | **Yes** — `update(**fields)` writes through to the JSON, in-memory state is thread-safe | End user via `PATCH /api/config` (frontend SettingsView) |

`RuntimeConfig.from_settings(settings, persist_path=...)` is the bridge: env values become defaults, JSON file overrides win.

## The discriminator

Ask: **"Does the user need to change this without restarting the gateway?"**

- **Yes** → `RuntimeConfig`. (LLM model swap, API base override, safe_mode toggle, embedding model change, threshold tuning.)
- **No** → `Settings`. (Vault path, credentials dir, gateway port, default tenant id, OpenFGA URL.)

If you can't decide, default to `RuntimeConfig`. The cost of demoting an env-only setting later is more invasive than promoting a user-tunable one to runtime.

## How to add a runtime-tunable field

1. **`bsage/core/runtime_config.py`** — add the field to `_ConfigState`:
   ```python
   @dataclass
   class _ConfigState:
       ...
       embedding_model: str = ""        # public — appears in snapshot()
       embedding_api_key: str = ""      # secret — add to _SECRET_FIELDS
       embedding_api_base: str | None = None
   ```
   And to `_SECRET_FIELDS` if it's an api key/token. The dataclass + `_STATE_FIELD_NAMES` introspection takes care of `update()`, `snapshot()`, persist, and `from_settings()` automatically.

2. **`bsage/core/config.py`** — add the same field to `Settings` so env vars seed it. Existing env names (`EMBEDDING_MODEL`, etc.) keep working as the initial value.

3. **`bsage/gateway/routes.py`** — add the field to the `ConfigUpdate` Pydantic model (`Optional`, defaults to `None`):
   ```python
   class ConfigUpdate(BaseModel):
       ...
       embedding_model: str | None = None
   ```
   The PATCH handler iterates `update.model_fields_set` and calls `runtime_config.update(**changes)` — no other handler edits needed.

4. **GET / PATCH `/api/config` response** — if the field is a secret, add a `has_<field>` boolean to the response (parallel to `has_llm_api_key`):
   ```python
   snap["has_embedding_api_key"] = bool(state.runtime_config.embedding_api_key)
   ```

5. **Components that read the value** — must hold a `RuntimeConfig` reference and re-read on every call (no caching). Pattern from `LiteLLMClient`:
   ```python
   class MyComponent:
       def __init__(self, runtime_config: RuntimeConfig) -> None:
           self._config = runtime_config
       async def use(self) -> ...:
           model = self._config.llm_model     # fresh on every call
   ```
   If the component is built once at AppState construction (e.g. `Embedder`), and you can't restructure it, build a fresh instance per call from a callable factory that reads `runtime_config`. This is the pattern in `bsage/gateway/canonicalization_routes.py:_embedder_callable`.

6. **`frontend/src/api/types.ts`** — add the field to `ConfigUpdate` (request) and `RuntimeConfig` (response).

7. **`frontend/src/components/settings/SettingsView.tsx`** — add an editable input + save button. Mirror the existing `llm_model` section pattern (eye-toggle for secrets, dot indicator for `has_*` state).

## Anti-pattern: the Settings-only trap

```python
# WRONG — embedding model is hard-coded at gateway boot
self.embedder = Embedder(
    model=settings.embedding_model,
    api_base=settings.embedding_api_base,
)

# RIGHT — same code path, but reads from RuntimeConfig (Settings is the seed)
self.embedder = Embedder(
    model=self.runtime_config.embedding_model,
    api_base=self.runtime_config.embedding_api_base,
)
```

The second form means a user can paste a Tailscale Ollama URL (`http://bsserver:11434`) into the SettingsView and have it take effect on the next request. The first form requires editing `.env` and redeploying.

## Anti-pattern: read-only frontend display

If the frontend currently renders a setting as read-only text (`<p>{config.embedding_model}</p>`), that's a tell — usually it should be an editable `<input>` like the LLM model section. The user can't tune what they can't edit.

## Verifying with tests

Two tests pin the contract:

```python
def test_secret_excluded_from_snapshot() -> None:
    cfg = _make_runtime_config(embedding_api_key="sk-secret")
    assert "embedding_api_key" not in cfg.snapshot()

def test_callable_reads_runtime_config_dynamically() -> None:
    state = MagicMock()
    state.runtime_config = _make_runtime_config()  # empty
    assert _embedder_callable(state) is None       # disabled

    state.runtime_config.update(embedding_model="ollama/test")
    assert _embedder_callable(state) is not None   # picked up without restart
```

The second test catches the most common regression: a downstream caller caching the value at construction time instead of re-reading on every call.

## Why this rule exists

BSage v1 is single-tenant per deployment but the `RuntimeConfig` layer is the seam where future per-tenant config will land — `from_settings(s, persist_path=...)` already takes a per-tenant persist path. Putting tunables on `Settings` works around the seam and locks them to the deployment. Putting them on `RuntimeConfig` keeps the future SaaS path open without code changes.

It also matches the existing user mental model: "I tune things in the SettingsView, like the LLM model." Surprising users with a setting that requires SSH + .env editing is an unforced UX hit.
