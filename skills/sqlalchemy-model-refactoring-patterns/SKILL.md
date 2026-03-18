# SQLAlchemy Model Refactoring: Field Removal & Migration Patterns

**Problem**: Removing mapped fields from SQLAlchemy models causes cascading failures in test fixtures, ORM instantiation, and API schemas.

**Context**: During BSNexus refactoring, removing `worker_id` and `reviewer_id` from Task model led to:
- TypeErrors in test helpers (Task.__init__ rejected the fields)
- 39 test file errors across multiple modules
- Need to synchronize ORM changes across 3 layers: models → schemas → tests

---

## Pattern: Field Removal Migration

### Phase 1: Identify Removal Scope
Before removing a field, find all references:
```bash
# Find model instantiation with field
grep -r "worker_id=" backend/tests/

# Find field assertions
grep -r "\.worker_id" backend/tests/

# Find schema definitions (Pydantic)
grep -r "worker_id" backend/src/schemas.py
```

**Lesson**: One field removal touches: ORM model → Pydantic schemas → API responses → test fixtures → test assertions.

### Phase 2: Update ORM Test Helpers FIRST
**Critical**: Update test fixture functions BEFORE running tests:

```python
# ❌ WRONG - causes cascade failures
def make_task(**kwargs) -> Task:
    return Task(
        id=kwargs.get("id", uuid.uuid4()),
        worker_id=kwargs.get("worker_id", None),  # Field doesn't exist anymore!
        ...
    )

# ✅ CORRECT - remove field from helper
def make_task(**kwargs) -> Task:
    return Task(
        id=kwargs.get("id", uuid.uuid4()),
        # worker_id removed entirely
        ...
    )
```

**Why**: SQLAlchemy's declarative constructor raises `TypeError: 'worker_id' is an invalid keyword argument` immediately. This breaks ALL tests using the helper.

### Phase 3: Staged Removal (For Large Codebases)

Instead of removing all at once:

1. **Mark deprecated with `@pytest.mark.skip`**:
   ```python
   @pytest.mark.skip(reason="Worker model removed in monolithic refactor")
   async def test_on_in_progress_sets_worker_id(...):
       ...
   ```

2. **Run tests to find remaining failures** (skip doesn't hide them):
   ```bash
   pytest tests/ --tb=short  # Shows skipped + failures
   ```

3. **Fix non-deprecated references**:
   - Update assertions that check the field
   - Remove field assertions from responses
   - Update schema definitions

4. **Finally, delete deprecated tests**:
   ```bash
   # Remove tests marked with skip
   grep -l "@pytest.mark.skip.*Worker" tests/*.py | xargs rm
   ```

**Result in this session**:
- Started: 512 total tests, 68 failures/errors
- Mark skipped: 58 deprecated tests, 454 passing
- After removal: 453 passing (100%), 0 skipped

### Phase 4: Update Dependent Layers

Remove from this order:
1. **ORM Model** (`models.py`) - remove the mapped field
2. **Schemas** (`schemas.py`) - remove Pydantic field
3. **Test Fixtures** (`tests/`) - remove from helpers & assertions
4. **API Handlers** (`api/`) - remove from responses
5. **Test Files** - remove deprecated test functions

**Pitfall**: Removing from model BEFORE updating test helpers causes immediate import/instantiation failures.

---

## Pattern: State Machine Handler Updates

When refactoring task pipeline, handlers may be missing:

```python
# Before: handlers incomplete
side_effect_map = {
    TaskStatus.ready: self._on_ready,
    TaskStatus.in_progress: self._on_in_progress,
    TaskStatus.done: self._on_done,
    # ❌ Missing: queued, review
}

# After: add handlers for new flow
side_effect_map = {
    TaskStatus.queued: self._on_queued,        # NEW
    TaskStatus.ready: self._on_ready,
    TaskStatus.in_progress: self._on_in_progress,
    TaskStatus.review: self._on_review,         # NEW
    TaskStatus.done: self._on_done,
}

# Add handler implementations
async def _on_queued(self, task: Task, **kwargs) -> None:
    if stream_manager is not None:
        await stream_manager.publish("tasks:queue", {
            "task_id": str(task.id),
            "repo_path": repo_path,  # Include repo context
            ...
        })
```

**Lesson**: Test failures like "Expected publish to be called once. Called 0 times" indicate missing side effect handler implementation.

---

## Checklist: Safe Field Removal

- [ ] Grep for all references (model, schemas, tests, API)
- [ ] Update test helpers FIRST (before running tests)
- [ ] Mark deprecated tests with `@pytest.mark.skip`
- [ ] Run tests to identify remaining failures
- [ ] Fix assertions that checked the field
- [ ] Update schema definitions (Pydantic)
- [ ] Fix API response tests
- [ ] Delete deprecated test functions
- [ ] Verify: run full test suite, expect no skips or failures

---

## Anti-Pattern: Test Coverage During Migration

During large refactoring, coverage may drop temporarily (62% → 88% → 100% in this session).

**Don't panic**:
- New modules (executor, architect_service) have 0% coverage initially
- As test infrastructure updates, coverage improves
- Focus on: core API tests pass, no failures (only skips during transition)

**Example metrics**:
- Start: 444/512 tests pass (87%), 68 errors
- After handler updates: 446 pass, 9 failures
- After cleanup: 453 pass (100%), 0 skipped
