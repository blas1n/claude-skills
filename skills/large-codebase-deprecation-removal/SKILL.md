---
name: large-codebase-deprecation-removal
description: "Large Codebase: Graceful Deprecation & Removal Strategy for distributed system patterns"
version: 1.0.0
---

# Large Codebase: Graceful Deprecation & Removal Strategy

**Problem**: Removing distributed system patterns (e.g., worker nodes) from large Python codebases causes hundreds of test failures across multiple layers.

**Context**: BSNexus worker node system removal (42 orchestrator tests, 16 state machine tests):
- Initial: 512 total tests
- After worker model removal: 68 errors/failures across 6+ test files
- Strategy: skip → fix → delete

---

## Strategy: 3-Phase Deprecation Lifecycle

### Phase 1: Mark as Deprecated (No Deletion Yet)

When you discover tests are testing removed functionality:

```python
# Don't delete immediately - mark first
@pytest.mark.skip(reason="Worker registry pattern removed in monolithic refactor")
async def test_on_in_progress_sets_worker_id(...):
    ...
```

**Why this phase?**
- Signals intent to other developers
- Allows tests to run (they're skipped, not erroring)
- Gives time to understand full scope
- Prevents merge conflicts if multiple people work on removal

**What to skip**:
- Tests for removed architectural patterns
- Tests for deleted feature sets
- Tests requiring external systems no longer in use

### Phase 2: Fix Everything Else

Run tests with skips in place:
```bash
pytest tests/ --tb=short -v
# Result: 57 skipped, 446 passed, 0 failed
```

Now fix the non-deprecated failures:
- Update test assertions (remove field checks)
- Update API response tests (remove deleted fields)
- Update test helpers/fixtures
- Fix state machine handler calls

**This phase's goal**: Zero failures, only skips.

In this session:
- 68 initial errors → systematic fixes → 453 passing
- Deprecated tests allowed us to see what else was broken

### Phase 3: Delete Deprecated Tests

Once all other tests pass:

```bash
# Remove one deprecated test file entirely
rm backend/tests/test_orchestrator.py  # 42 tests

# Remove individual deprecated test functions
python3 << 'EOF'
import re
with open('tests/file.py', 'r') as f:
    content = f.read()
# Remove all @pytest.mark.skip marked functions
pattern = r'@pytest\.mark\.skip\([^)]*\)\n(async def test_[^(]*\([^)]*\).*?)(?=\n@|\nclass |\ndef |\Z)'
content = re.sub(pattern, '', content, flags=re.DOTALL)
with open('tests/file.py', 'w') as f:
    f.write(content)
EOF
```

**Final state**: Zero skips, all tests passing.

---

## Pattern: Test File-Level Deprecation

For complete features being removed (e.g., worker system):

```bash
# Option 1: Delete entire test file
rm backend/tests/test_orchestrator.py

# Option 2: If file has mix of old/new tests
# 1. Mark all deprecated tests with @pytest.mark.skip
# 2. Fix non-deprecated tests
# 3. Remove deprecated tests with regex/script
# 4. Delete file if empty
```

**In this session**:
- `test_orchestrator.py` (42 tests) → deleted entire file
- `test_state_machine.py` (16 deprecated) → removed functions, kept 44 working tests
- Individual test functions (test_get_board_workers) → removed from files

---

## Mapping: What Gets Removed at Each Phase

| Item | Phase 1 | Phase 2 | Phase 3 |
|------|---------|---------|---------|
| Worker model fields | ✅ Removed | - | - |
| Test fixture parameters | ✅ Updated | - | - |
| Test assertions on removed fields | - | ✅ Updated | - |
| @pytest.mark.skip functions | - | ✅ Applied | ✅ Deleted |
| Orchestrator test file | - | - | ✅ Deleted |
| Worker registry imports | - | ✅ Removed | - |

---

## Metrics for Success

Track these during removal:

```
Starting state:
- 512 total tests
- 68 errors/failures
- Coverage: 62%

After Phase 1 (mark skipped):
- 512 total tests
- 57 skipped
- 455 passing
- 0 failures

After Phase 2 (fix everything else):
- 495 total tests (removed skipped files)
- 0 skipped
- 495 passing
- 0 failures

Final state:
- 453 total tests (some files deleted)
- 0 skipped
- 453 passing (100%)
- Coverage: back to normal levels
```

---

## Red Flags During Removal

🚩 **"Tests are still using deleted model fields"**
- Solution: Update test assertions to not check removed fields
- Example: Remove `assert task.worker_id is None`

🚩 **"Import errors in test fixtures"**
- Solution: Test helpers (make_task) reference removed fields
- Action: Remove field from helper kwargs immediately

🚩 **"Coverage dropped dramatically"**
- Normal during refactoring
- New code (executor, architect_service) has 0% coverage
- As tests update, coverage normalizes
- Don't panic unless failures appear

🚩 **"One test file has 30+ skipped tests"**
- Consider deleting entire file instead of selectively removing
- Simpler: `rm test_orchestrator.py` vs maintaining many skips

---

## Command Reference: Bulk Operations

### Remove all @pytest.mark.skip functions from file:
```bash
python3 << 'EOF'
import re
filename = 'backend/tests/test_state_machine.py'
with open(filename, 'r') as f:
    content = f.read()
pattern = r'@pytest\.mark\.skip\([^)]*\)\n(async def test_[^(]*\([^)]*\).*?)(?=\n@|\nclass |\nndef |\Z)'
content = re.sub(pattern, '', content, flags=re.DOTALL)
with open(filename, 'w') as f:
    f.write(content)
print(f"Removed deprecated tests from {filename}")
EOF
```

### Find all references to removed field:
```bash
grep -r "worker_id" backend/ --include="*.py" | grep -v ".pyc"
```

### Find tests marked as skip:
```bash
grep -r "@pytest.mark.skip" backend/tests/ | wc -l
```

### Count tests in file:
```bash
grep -c "^async def test_\|^def test_" backend/tests/file.py
```
