---
name: pytest-asyncmock-unawaited-coroutine
description: Patching async stdlib functions (asyncio.sleep, asyncio.create_subprocess_exec) with AsyncMock causes RuntimeWarning about unawaited coroutines during test teardown
---

# pytest AsyncMock Unawaited Coroutine Warning

## Problem

When patching async stdlib functions in pytest, a `RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited` appears during test teardown.

- **Symptom**: Warning appears in pytest output attributed to a test that passes. Warning persists across test runs and migrates between tests when you fix one instance.
- **Root cause**: Python 3.11's `unittest.mock` auto-detects async targets and creates `AsyncMock` internally. During garbage collection or `inspect` signature introspection, the mock's internal coroutine machinery creates coroutines that are never awaited.
- **Common mistake**: Trying to fix it per-test with `@pytest.mark.filterwarnings` or switching between `side_effect=`, `new_callable=`, `new=` — the warning moves to other tests because the root cause is in the mock machinery itself, not in any single test.

## Failed Approaches (in order tried)

1. `patch("asyncio.sleep", side_effect=fake_async_fn)` — Still creates internal AsyncMock
2. `patch("asyncio.sleep", new_callable=AsyncMock)` — Same root issue
3. `@pytest.mark.filterwarnings("ignore::RuntimeWarning")` — Warning emitted during teardown, not during test
4. `@pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")` — Same teardown timing issue
5. `patch("asyncio.sleep", new=fake_async_fn)` — Fixes THIS test but warning migrates to other tests using `patch("asyncio.create_subprocess_exec", return_value=mock_proc)`

## Solution

Two-layer fix:

### Layer 1: Use `new=` with plain async functions (not AsyncMock)

Replace `AsyncMock` with real async functions to avoid mock coroutine machinery:

```python
# BAD: Creates internal AsyncMock coroutines
with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
    await some_function()
mock_sleep.assert_awaited_once_with(42)

# GOOD: No mock machinery, no unawaited coroutines
sleep_args: list[float] = []
async def fake_sleep(seconds: float) -> None:
    sleep_args.append(seconds)
with patch("asyncio.sleep", new=fake_sleep):
    await some_function()
assert sleep_args == [42]
```

For exception-raising patches, use `MagicMock` (sync) instead of letting patch auto-detect:

```python
# BAD: patch auto-detects async target, creates AsyncMock
with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError("not found")):
    ...

# GOOD: Explicit sync MagicMock — exception fires before any coroutine is created
with patch("asyncio.create_subprocess_exec", new=MagicMock(side_effect=FileNotFoundError("not found"))):
    ...
```

### Layer 2: Global filterwarnings for residual cases

Some `return_value=mock_proc` patterns still trigger the warning during GC. Suppress globally in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
filterwarnings = [
    "ignore:coroutine.*was never awaited:RuntimeWarning",
]
```

## Key Insights

- `patch()` auto-detects whether the target is a coroutine function and creates `AsyncMock` even when you pass `side_effect=` or `return_value=`. The `new=` parameter is the ONLY way to fully bypass this detection.
- The warning migrates between tests because it's triggered by GC timing, not by the test that created the mock. Fixing one test just changes which test's teardown triggers GC.
- Per-test `filterwarnings` markers don't work because the warning is emitted during teardown/GC, outside the test's warning context.

## Red Flags

- `RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited` in pytest output
- Warning attributed to a test that passes and looks correct
- Warning moves to a different test after you "fix" the original test
- Patching any `asyncio.*` function with `patch()` without explicit `new=`
