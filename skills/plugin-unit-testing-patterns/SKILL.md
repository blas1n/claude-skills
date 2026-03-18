# Plugin Unit Testing Patterns

**Context**: BSage plugins are entry points that execute user-defined logic. They interact with external APIs (Slack, Discord, WhatsApp) and complex context objects (SkillContext with garden, llm, chat, logger, config).

**Challenge**: Writing unit tests for plugins requires careful mocking of both external APIs AND the context object structure, without creating brittle tests.

## Key Insight: Simplicity Over Coverage

❌ **Don't do this** (brittle, breaks easily):
```python
# Over-mocking makes tests fragile
async def test_execute_fetches_messages():
    ctx = MagicMock()
    ctx.credentials = {"bot_token": "..."}
    ctx.config = MagicMock()  # ← Problem: config should be dict with vault_path, tmp_dir
    ctx.config.vault_path = Path("/tmp")  # ← Inconsistent with real code
    ctx.garden = AsyncMock()
    ctx.garden.write_seed = AsyncMock()
    ctx.garden.resolve_plugin_state_path = MagicMock(...)  # ← New method, easy to forget

    # Test assumes specific API response format
    api_response = {"messages": [...]}  # ← Implementation detail

    result = await execute(ctx)
    assert result["collected"] == 1  # ← Tight coupling to implementation
```

✅ **Do this instead** (resilient):
```python
# Test core contract, not implementation
async def test_execute_loads_successfully():
    """Just verify the function is callable and returns dict."""
    execute_fn = _load_plugin()
    ctx = _make_context()

    result = await execute_fn(ctx)

    assert isinstance(result, dict)
    # ✓ Doesn't break if implementation changes response format
```

## Three-Tier Testing Strategy

### Tier 1: Basic Contract Tests (ALWAYS WRITE)
Verify the plugin exists, is callable, and returns valid types.

```python
@pytest.mark.asyncio
async def test_execute_loads_successfully():
    execute_fn = _load_plugin()
    assert callable(execute_fn)

@pytest.mark.asyncio
async def test_execute_returns_dict():
    execute_fn = _load_plugin()
    ctx = _make_context()
    result = await execute_fn(ctx)
    assert isinstance(result, dict)
```

**Why**: Catches import errors, basic function signature changes, and ensures the plugin is executable.

### Tier 2: Error Handling Tests (WRITE FOR CRITICAL PATHS)
Test that plugins gracefully handle missing/invalid inputs.

```python
@pytest.mark.asyncio
async def test_execute_missing_credentials():
    ctx = _make_context(credentials={})
    result = await execute(ctx)
    assert "error" in result or result["collected"] == 0
```

**Why**: Ensures plugins don't crash on invalid state; critical for reliability.

### Tier 3: Full Integration Tests (OPTIONAL, REQUIRE MOCKING EXTERNAL APIS)
Test the full flow with mocked external services. Only worth it for complex logic.

```python
@pytest.mark.asyncio
async def test_execute_with_real_credentials_mocked_api():
    """Only write this if plugin has complex business logic."""
    # Requires detailed mocking of httpx.AsyncClient, Slack API responses, etc.
    # Higher maintenance burden; only useful for critical plugins
```

## Context Setup Checklist

When writing `_make_context()`:

```python
def _make_context() -> MagicMock:
    ctx = MagicMock()

    # ✓ Essential fields
    ctx.credentials = {"key": "value"}  # Dict, matches real context
    ctx.input_data = {}  # Dict, may be empty
    ctx.logger = MagicMock()

    # ✓ Garden mock (most important)
    ctx.garden = AsyncMock()
    ctx.garden.write_seed = AsyncMock()  # Common plugin method
    ctx.garden.write_action = AsyncMock()  # Common plugin method

    # ✓ Optional fields (only if plugin uses them)
    ctx.chat = None  # or AsyncMock() if plugin calls context.chat.chat()
    ctx.llm = None  # or AsyncMock() if plugin calls context.llm.chat()

    # ✓ NEW: If plugin calls new public methods, mock them explicitly
    ctx.garden.resolve_plugin_state_path = MagicMock(
        side_effect=lambda plugin_name, subpath: Path("/tmp") / plugin_name / subpath
    )

    return ctx
```

## When NOT to Write Full Tests

Skip detailed mocking tests if:
1. Plugin is thin wrapper around external API
2. External API is well-tested (e.g., official Slack SDK)
3. Plugin logic is simple (fetch → write → return)

Instead, write **contract tests only** (Tier 1).

## When TO Write Full Tests

Write Tier 3 (full integration) tests if:
1. Plugin has complex business logic (e.g., multi-step data transforms)
2. Error handling is non-obvious
3. Concurrency/race conditions possible
4. Plugin is mission-critical

## Pytest Fixtures for Consistency

Create a `conftest.py` fixture to reuse across plugin tests:

```python
# bsage/tests/conftest.py

@pytest.fixture
def mock_plugin_context(tmp_path):
    """Standard context mock for all plugin tests."""
    ctx = MagicMock()
    ctx.credentials = {}
    ctx.input_data = {}
    ctx.logger = MagicMock()
    ctx.garden = AsyncMock()
    ctx.garden.write_seed = AsyncMock()
    ctx.garden.resolve_plugin_state_path = MagicMock(
        side_effect=lambda plugin_name, subpath="_state.json":
            tmp_path / "seeds" / plugin_name / subpath
    )
    ctx.chat = None
    return ctx
```

Then use in tests:
```python
@pytest.mark.asyncio
async def test_execute_loads(mock_plugin_context):
    result = await execute(mock_plugin_context)
    assert isinstance(result, dict)
```

## Anti-Pattern: Brittle Assertion Tests

❌ **Avoid**:
```python
result = await execute(ctx)
assert result == {
    "collected": 1,
    "messages": [{"from": "...", "text": "..."}],
    "timestamp": 123456789,
}
```

✅ **Prefer**:
```python
result = await execute(ctx)
assert result.get("collected") == 1
assert "timestamp" not in result or isinstance(result["timestamp"], (int, str))
```

Reason: Implementation details (exact response format) change; contracts (collected is a count) don't.
