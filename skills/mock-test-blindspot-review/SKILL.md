---
name: mock-test-blindspot-review
description: "When reviewing code with high mock-test coverage (80%+), systematically check for integration-level bugs that mocked tests hide: wrong method calls with correct signatures, missing dependency wiring, and asymmetric error handling across sibling methods."
---

# Mock Test Blindspot Review

## Problem

Projects with high mock-test coverage (80%+) create a false sense of safety. Mocked tests verify **interface contracts** but miss **semantic correctness** and **dependency wiring**. This leads to a specific class of bugs that pass all tests but fail in production.

## When to Apply

- Reviewing branches with many new modules and high coverage
- After seeing "all tests pass" but before approving merge
- When modules interact through dependency injection (constructor wiring)

## Three Blindspot Categories

### 1. Wrong Argument Semantics (Mock Ignores Value Meaning)

**Pattern**: Method A calls Method B with a syntactically valid but semantically wrong argument. Mock returns success regardless.

**Example discovered**:
```python
# maintenance.py called:
count = await self._graph.count_relationships_for_entity(type_name)
# type_name = "idea" (entity TYPE), but method expects a note PATH like "ideas/bsage.md"
# Mock returns 0 for any input → test passes, production silently fails
```

**Check**: For every mock call, verify the argument's **domain** matches what the real implementation expects. Ask: "Would the real method produce the correct result with this exact argument?"

### 2. Missing Dependency Wiring (Unit Tests Inject Directly)

**Pattern**: Unit tests construct objects with all dependencies explicitly provided. But the actual application factory/bootstrap code forgets to pass a dependency.

**Example discovered**:
```python
# dependencies.py:
self.graph_extractor = GraphExtractor(llm_extractor=self.llm_extractor)
# Missing: ontology=self.ontology
# Tests pass because they construct GraphExtractor(ontology=mock_ontology) directly
```

**Check**: Read the **application wiring code** (factories, dependency injection, FastAPI dependencies) and verify every optional parameter that tests provide is also provided in production construction.

### 3. Asymmetric Sibling Methods (Fix One, Miss the Other)

**Pattern**: Two methods with similar structure have the same vulnerability. A fix is applied to one but not the other.

**Example discovered**:
```python
# embed() got empty response check:
if not response.data:
    raise RuntimeError("Embedding response contains no data")

# embed_many() had the SAME vulnerability but was missed in Round 1
sorted_data = sorted(response.data, ...)  # crashes if response.data is None
```

**Check**: After fixing a bug, search for sibling/parallel methods with the same pattern. Use grep for the vulnerable pattern across the file.

## Review Checklist

When reviewing a branch with mock-heavy tests:

1. **Wiring audit**: Read the top-level factory/bootstrap code. For each constructor call, verify all optional dependencies are passed
2. **Argument semantics**: For key mock assertions (`assert_awaited_with`, `call_args`), verify the argument makes sense for the REAL implementation
3. **Sibling symmetry**: After identifying a fix, grep for the same pattern in related methods
4. **Error path symmetry**: If method A has error handling added, check if method B (same class, same pattern) also needs it

## Origin

Discovered during BSage v2.2 branch review (2026-03-17). 4 rounds of sub-agent review were needed because each round uncovered a new bug from a different blindspot category. All bugs passed 1011 tests at 90%+ coverage.
