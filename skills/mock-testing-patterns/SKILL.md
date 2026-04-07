---
name: mock-testing-patterns
description: "Mock testing patterns — context setup gotchas, blindspot review for high-coverage code, plugin testing tiers"
version: 1.0.0
triggers:
  - pattern: "writing mocks for complex objects, reviewing high mock-coverage code, or testing plugin systems"
---

# Mock Testing Patterns

## 1. Context Setup Gotchas

### New methods need explicit mocking
When adding a public method, all test contexts that mock the class must be updated:

```python
# ❌ AsyncMock() auto-generates coroutine for unknown methods
ctx.garden = AsyncMock()
ctx.garden.resolve_plugin_state_path("slack")  # Returns coroutine, not Path

# ✅ Explicitly mock new methods
ctx.garden.resolve_plugin_state_path = MagicMock(
    side_effect=lambda name, sub="_state.json": Path("/tmp") / name / sub
)
```

### AsyncMock base makes all attributes async
Using `AsyncMock()` as base makes **every attribute** return async — even sync methods:

```python
# ❌ db.add() becomes async even though SQLAlchemy add() is sync
mock_db = AsyncMock()

# ✅ MagicMock base, only truly async methods get AsyncMock
mock_db = MagicMock()
mock_db.add = MagicMock()       # sync
mock_db.execute = AsyncMock()   # async
mock_db.commit = AsyncMock()    # async
```

**Rule**: `MagicMock()` as base for mixed sync/async objects.

### MagicMock auto-creates any attribute (incl. private ones)
`getattr(mock_task, "_bound_agent", None)` returns a MagicMock (truthy!), not None.

```python
# ❌ getattr fallback is useless against MagicMock
agent = getattr(task, "_bound_agent", None)  # Always truthy for MagicMock task

# ✅ Duck-type check: verify the attribute has the expected type
agent = getattr(task, "_bound_agent", None)
if agent and isinstance(getattr(agent, "executor_type", None), str):
    # Real agent, not auto-generated MagicMock attr
```

### SQLAlchemy models can't use `__new__` for test stand-ins
`Agent.__new__(Agent)` skips `__init__` → no `_sa_instance_state` → attribute assignment crashes.

```python
# ❌ Crashes: AttributeError: 'Agent' object has no attribute '_sa_instance_state'
agent = Agent.__new__(Agent)
agent.executor_type = "bsgateway"

# ✅ Use a dataclass stand-in for unit tests
@dataclass
class FakeAgent:
    executor_type: str = "claude_api"
    executor_config: dict | None = None
    system_prompt: str | None = None
```

### MagicMock breaks comparison operators (silent TypeError → infinite loop)
`getattr(mock, "int_field", default)` returns MagicMock (truthy), so `or default` never fires.
Then comparison operators (`>=`, `<=`, `==`) with int raise `TypeError` in Python 3:

```python
# ❌ Hang: getattr returns MagicMock, "or 1" doesn't fire, then >= raises TypeError
#    If caught by broad except → infinite retry loop
mock_project = MagicMock()
max_c = getattr(mock_project, "max_concurrent_tasks", 1) or 1  # MagicMock!
if active_count >= max_c:  # TypeError: '>=' not supported

# ✅ Always set numeric/string attributes explicitly on MagicMock
mock_project = MagicMock()
mock_project.max_concurrent_tasks = 1
mock_project.workspace_dir = None
```

**Rule**: When mocking objects with numeric attributes used in comparisons,
always set them explicitly. MagicMock auto-attributes are truthy and non-comparable.

### Patching locally-imported symbols
`from x import Y` inside a function body: patch at source, not caller:

```python
# ❌ ProjectRepository not in state_machine's namespace
with patch("myapp.core.state_machine.ProjectRepository"): ...

# ✅ Patch at source
with patch("myapp.repositories.project_repository.ProjectRepository.get_by_id",
           new=AsyncMock(return_value=None)): ...
```

---

## 2. Mock Test Blindspot Review

High mock-test coverage (80%+) hides integration-level bugs. Three categories:

### Wrong Argument Semantics
Mock returns success regardless of argument meaning:
```python
# Mock accepts type_name="idea" but real method expects note_path="ideas/bsage.md"
count = await self._graph.count_relationships_for_entity(type_name)
```
**Check**: Would the real method produce correct results with this exact argument?

### Missing Dependency Wiring
Unit tests construct objects with all deps explicitly, but factory code forgets one:
```python
# Tests: GraphExtractor(ontology=mock_ontology) ← works
# Production: GraphExtractor(llm_extractor=self.llm_extractor) ← missing ontology!
```
**Check**: Read application wiring code, verify every optional param tests provide is also in production.

### Asymmetric Sibling Methods
Fix applied to one method, missed in sibling with same pattern:
```python
# embed() got empty response check, embed_many() didn't
```
**Check**: After fixing a bug, grep for same pattern in related methods.

### Review Checklist
- [ ] Wiring audit: read factory/bootstrap, verify all optional deps passed
- [ ] Argument semantics: verify mock call args make sense for real impl
- [ ] Sibling symmetry: grep for same vulnerable pattern
- [ ] Error path symmetry: if method A gets error handling, check method B

---

## 3. Plugin Testing Tiers

### Tier 1: Contract Tests (ALWAYS)
```python
async def test_execute_returns_dict():
    result = await execute(_make_context())
    assert isinstance(result, dict)
```

### Tier 2: Error Handling (CRITICAL PATHS)
```python
async def test_execute_missing_credentials():
    result = await execute(_make_context(credentials={}))
    assert "error" in result or result["collected"] == 0
```

### Tier 3: Full Integration (COMPLEX LOGIC ONLY)
Full flow with mocked external services. Higher maintenance — only for critical plugins.

### Context Factory Pattern
```python
def _make_context(credentials=None, tmp_path=Path("/tmp")) -> MagicMock:
    ctx = MagicMock()
    ctx.credentials = credentials or {"key": "value"}
    ctx.input_data = {}
    ctx.logger = MagicMock()
    ctx.garden = AsyncMock()
    ctx.garden.write_seed = AsyncMock()
    ctx.garden.resolve_plugin_state_path = MagicMock(
        side_effect=lambda name, sub="_state.json": tmp_path / name / sub
    )
    return ctx
```
