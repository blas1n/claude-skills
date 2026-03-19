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

## Gotcha 2: AsyncMock() as Base Mock — All Attributes Become Async

**Problem**: Using `AsyncMock()` as the base mock object makes **every attribute access** return an `AsyncMock` instance, including attributes that correspond to synchronous methods. Any sync call on those attributes produces an unawaited coroutine → `RuntimeWarning: coroutine was never awaited`.

```python
# ❌ AsyncMock base — db.add() becomes async even though it's sync in SQLAlchemy
mock_db = AsyncMock()
mock_db.add(task)  # Returns coroutine, never awaited → RuntimeWarning

# ✅ MagicMock base — only truly async methods get AsyncMock
mock_db = MagicMock()
mock_db.add = MagicMock()      # sync — SQLAlchemy add() is synchronous
mock_db.execute = AsyncMock()  # async — awaited in production code
mock_db.flush = AsyncMock()    # async
mock_db.commit = AsyncMock()   # async
```

**Rule**: Use `MagicMock()` as the base for any object that mixes sync/async methods. Only assign `AsyncMock()` to methods that are explicitly `await`-ed in production code.

## Gotcha 3: Patching Locally-Imported Symbols

**Problem**: `unittest.mock.patch()` patches an attribute in a module's **namespace**. If production code uses a local import (`from x import Y` inside a function body), `Y` is never added to the calling module's namespace — `patch("calling_module.Y")` raises `AttributeError: module does not have attribute 'Y'`.

```python
# production code: state_machine.py
async def _get_repo_path(self, task, db):
    from backend.src.repositories.project_repository import ProjectRepository  # local import
    repo = ProjectRepository(db)
    project = await repo.get_by_id(task.project_id)
    return project.repo_path if project else ""

# ❌ Wrong patch path — ProjectRepository is NOT in state_machine's namespace
with patch("backend.src.core.state_machine.ProjectRepository") as mock:
    ...  # AttributeError: module has no attribute 'ProjectRepository'

# ✅ Patch at the source where the symbol actually lives
with patch(
    "backend.src.repositories.project_repository.ProjectRepository.get_by_id",
    new=AsyncMock(return_value=None),
):
    result = await state_machine._get_repo_path(task, mock_db)
```

**Rule**: When patching a locally-imported symbol, always patch it at `<source_module>.<ClassName>.<method>` or use `patch.object()` on the class directly. Never try to patch it in the calling module.

## Related Patterns

- **Private methods**: Don't need to mock (tests shouldn't call them directly)
- **Properties**: Mock as attributes, not methods: `ctx.garden.result = expected_value`
- **Async methods in mock**: Use `AsyncMock()` if the method should return a coroutine, `MagicMock()` if it should return a value
