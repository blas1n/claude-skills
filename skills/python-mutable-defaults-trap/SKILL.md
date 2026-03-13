# Python Mutable Defaults Trap

## When to apply

When you see any of these patterns:
- Module-level `dict` or `list` used as a default/template that gets copied
- `dict(some_default)` or `list(some_default)` to create "independent" copies
- Factory functions that return from a module-level mutable object
- Test fixtures or config loaders that start from a shared default

## The Problem

`dict()` and `list()` only perform **shallow copies**. Nested mutable objects (dicts, lists, sets) remain shared references. Mutations to nested values leak across all "copies".

```python
# BUG: nested dicts are shared references
_DEFAULTS = {"entity_types": {"note": {}, "person": {}}}

def get_config():
    return dict(_DEFAULTS)  # SHALLOW copy only!

a = get_config()
a["entity_types"]["food"] = {}  # Mutates _DEFAULTS too!
```

## The Fix

Always use `copy.deepcopy()` for nested mutable structures:

```python
import copy

_DEFAULTS = {"entity_types": {"note": {}, "person": {}}}

def get_config():
    return copy.deepcopy(_DEFAULTS)  # Safe: fully independent copy
```

## Detection Checklist

1. Is there a module-level `dict`/`list` with nested mutables?
2. Is it copied with `dict()`, `list()`, `.copy()`, or `{**d}`?
3. Are nested values ever mutated after copying?

If all three are yes -> replace with `copy.deepcopy()`.

## Related: YAML Date Auto-Parsing

PyYAML and `yaml.safe_load` parse bare date-like values (`2026-03-12`) as `datetime.date` objects, not strings. When asserting YAML-parsed frontmatter values in tests:

```python
# BAD: fails because value is datetime.date, not str
assert props["captured_at"] == "2026-03-12"

# GOOD: convert to string first
assert str(props["captured_at"]) == "2026-03-12"
```

## Related: Sync-to-Async Refactor Mock Mismatch

When refactoring a sync function to async, all test mocks must change from `MagicMock` to `AsyncMock`:

```python
# Before refactor (sync)
mock.extract_from_note = MagicMock(return_value=result)

# After refactor (async) - MUST change to AsyncMock
mock.extract_with_llm = AsyncMock(return_value=result)
```

Symptom: test returns a coroutine object instead of the expected value, or `TypeError: object MagicMock can't be used in 'await' expression`.
