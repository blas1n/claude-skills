---
name: lru-cached-settings-pin-env-across-test-modules
description: An `@lru_cache` settings factory is a process-wide singleton, so the FIRST test module to touch it pins its monkeypatched env for the whole run. A second module setting a different secret/URL gets the first module's value — symptom is "passes alone, fails when run together" with a signature/connection error that points at the wrong thing.
category: trap
---

# `@lru_cache`d settings pin env across test modules

## Problem

Config factories are cached so construction cost is paid once:

```python
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide Settings singleton (cached)."""
    return Settings()          # reads os.environ via pydantic-settings
```

Two test modules each set their own secret and mint tokens with it:

```python
# tests/api/test_a.py
monkeypatch.setenv("USER_JWT_SECRET", "test-session-secret")

# tests/mcp/test_b.py
monkeypatch.setenv("USER_JWT_SECRET", "e2e-session-secret")
```

Whichever module runs first populates the cache. The second signs with its own
secret while the server still verifies with the first one:

```
{"detail":"user JWT verification failed: Signature verification failed"}
```

The tells:

- **Passes alone, fails together.** `pytest tests/api/test_a.py` is green;
  `pytest tests/mcp/test_b.py tests/api/test_a.py` is red. Run order decides
  which module wins, so it can also flip when you add an unrelated test file.
- **The error blames the wrong layer.** "Signature verification failed" reads as
  a bug in token minting or key handling, not as config caching.
- `monkeypatch` is doing its job perfectly — `os.environ` *is* correct. Nothing
  re-reads it.

Same shape for any cached factory: a DB URL, an issuer, a feature flag, an API
base. Anything behind `@lru_cache` / a module-level singleton.

## Solution

### Clear every cached factory the module influences, on both edges

Not just the obvious one. A request often touches several settings objects
(app config, authz config, worker config), each independently cached:

```python
@pytest_asyncio.fixture
async def db(monkeypatch):
    monkeypatch.setenv("USER_JWT_SECRET", SESSION_SECRET)
    monkeypatch.setenv("BSVIBE_OAUTH_ISSUER", ISSUER)
    get_settings.cache_clear()
    # authz Settings is @lru_cache(maxsize=1): whichever module touches it first
    # would otherwise pin its USER_JWT_SECRET for the whole process.
    get_authz_settings.cache_clear()
    yield ...
    get_settings.cache_clear()          # clear on teardown too — the NEXT
    get_authz_settings.cache_clear()    # module inherits whatever you left
```

Clearing only on setup leaves your value pinned for everyone after you.

### Find the cached factories

```bash
grep -rn "lru_cache\|@cache" backend/ --include="*.py" | grep -B2 -i "settings\|config"
```

Then confirm which ones the code path under test actually reads — the import
site tells you: `from x.settings import get_settings as get_authz_settings`.

### Diagnose an existing flake

If a test passes alone and fails in a suite, bisect by pairing rather than
reading the failing test:

```bash
pytest tests/suspect_module.py tests/failing_module.py::test_x -q
```

A pass alone plus a fail when paired is near-conclusive for shared process
state; cached settings are the first place to look.

## Related

- `env-gated-test-backend-local-red-not-ci-red`
- `pytest-singleton-async-resource-cross-loop-leak`
- `feedback_drift_guard_cache_stale`
