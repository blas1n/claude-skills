# Mock Context Setup Gotchas

**Problem**: When adding new methods to a class, mocking the object but forgetting to mock the new methods causes tests to fail with `AttributeError` or return MagicMock coroutines instead of values.

**When it happens**: Refactoring adds a new public method (e.g., `resolve_plugin_state_path()`), existing test mocks don't include this method, and tests that call the new method fail.

## The Failure Pattern

```python
# You add a new public method:
class GardenWriter:
    def resolve_plugin_state_path(self, plugin_name: str) -> Path:
        return self._vault.resolve_path(f"seeds/{plugin_name}/_state.json")

# But your test mock is still the old version:
ctx.garden = AsyncMock()  # ❌ No resolve_plugin_state_path!

# Then the plugin code calls:
state_path = context.garden.resolve_plugin_state_path("slack-input")
# ⚠️ Returns a coroutine MagicMock instead of Path
# Later when you do: state_path.exists()
# TypeError: 'coroutine' object has no attribute 'exists'
```

## Solution: Explicitly Mock New Methods

When adding a public method, update ALL test contexts that mock the class:

```python
def _make_context(vault_root: Path | None = None) -> MagicMock:
    ctx = MagicMock()
    ctx.garden = AsyncMock()

    # ✅ Explicitly mock the new public method
    ctx.garden.resolve_plugin_state_path = MagicMock(
        side_effect=lambda plugin_name, subpath="_state.json":
            (vault_root or Path("/tmp")) / "seeds" / plugin_name / subpath
    )
    return ctx
```

## Checklist: After Adding a Public Method

- [ ] Add the method implementation
- [ ] Search for all test files that mock this class
- [ ] Add `MagicMock(side_effect=...)` for each new public method in ALL test contexts
- [ ] Run tests to verify mocks work as expected
- [ ] If the method is async, check if it should return a coroutine or resolved value in tests

## Related Patterns

- **Private methods**: Don't need to mock (tests shouldn't call them directly)
- **Properties**: Mock as attributes, not methods: `ctx.garden.result = expected_value`
- **Async methods in mock**: Use `AsyncMock()` if the method should return a coroutine, `MagicMock()` if it should return a value
