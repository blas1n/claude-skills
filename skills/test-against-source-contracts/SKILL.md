---
name: test-against-source-contracts
description: "Test Against Source Contracts — verify tests match actual API/interface contracts"
version: 1.0.0
---

# Test Against Source Contracts

## When to Use

When writing tests for code that involves:
- Event systems (EventBus, emit/subscribe patterns)
- Decorator-based registration (plugin decorators, route decorators)
- Dataclass/model constructors with required fields
- String assertions where values share common prefixes

## Problem

Tests written against **assumed** interfaces fail at runtime because the actual source code uses different:
- Attribute names (`__plugin__` vs `_plugin_meta`)
- Object structures (`Event` dataclass vs plain string)
- Required constructor fields (dataclass fields without defaults)
- String matching semantics (substring containment vs exact match)

## Rules

### 1. Always Read Decorator Source Before Testing Metadata

```python
# WRONG — guessing attribute name
meta = execute._plugin_meta  # AttributeError!

# RIGHT — read the decorator source first to find actual attribute
# If decorator does: fn.__plugin__ = {...}
meta = execute.__plugin__
```

**Before writing a test that accesses decorator-attached metadata, read the decorator implementation to find the exact attribute name.**

### 2. Always Read Event System Source Before Asserting Events

```python
# WRONG — assuming emit receives a string
event_bus.emit.assert_called()
assert call_args[0][0] == "NOTE_UPDATED"  # Fails: receives Event object

# RIGHT — check what emit_event() actually constructs
from app.core.events import EventType
assert call_args[0][0].event_type == EventType.NOTE_UPDATED
```

**Event helpers often wrap raw strings into typed Event objects. Read `emit_event` / `emit` to see what the subscriber actually receives.**

### 3. Always Check Dataclass Required Fields

```python
# WRONG — missing required field
record = ProvenanceRecord(
    entity_id=eid, source_path="a.md",
    extraction_method="rule", confidence=1.0
)  # TypeError: missing 'extracted_at'

# RIGHT — read the dataclass definition, provide all fields without defaults
record = ProvenanceRecord(
    entity_id=eid, source_path="a.md",
    extraction_method="rule", confidence=1.0,
    extracted_at="2026-01-01T00:00:00",
)
```

**Before constructing a dataclass in tests, read its definition to identify ALL required fields (those without default values).**

### 4. Use Boundary-Aware String Assertions

```python
# WRONG — substring match gives false positive
assert "status: seed" not in content  # Fails when content has "status: seedling"

# RIGHT — include line boundary
assert "status: seed\n" not in content  # Only matches exact "seed" value

# ALSO RIGHT — use regex for precision
import re
assert not re.search(r"status:\s*seed\b", content)
```

**When asserting absence of a string value, ensure the assertion accounts for values that share a common prefix (seed/seedling, test/testing, etc.).**

## Checklist

Before writing any test:
- [ ] Read the source implementation of the function/class under test
- [ ] For decorators: find the exact attribute name set on the decorated function
- [ ] For events: trace the full emit path to see the final object structure
- [ ] For dataclasses: list all required fields (no default value)
- [ ] For string assertions: check if any valid values are prefixes of other valid values
