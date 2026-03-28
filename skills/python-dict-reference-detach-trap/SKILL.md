---
name: python-dict-reference-detach-trap
description: "Python Dict Reference Detach Trap — filtering list value then removing key detaches the reference"
version: 1.0.0
---

# Python Dict Reference Detach Trap

## Trigger
When modifying a dict's list value via filtering (list comprehension) and then conditionally removing the key, while also appending to the filtered list afterward.

## Problem Pattern

```python
# In-memory rate limiter / sliding window pattern
_store: dict[str, list[float]] = defaultdict(list)

def check(key: str) -> None:
    now = time.monotonic()
    # BUG: window is a NEW list, not a reference to _store[key]
    window = [t for t in _store[key] if now - t < 60]

    # Removing the key when empty seems like a good cleanup...
    if not window:
        _store.pop(key, None)  # key removed from dict
    else:
        _store[key] = window   # only reassigned when non-empty

    # ...but append goes to the orphaned local list, NOT the dict
    window.append(now)
    # Result: timestamps are never accumulated. Rate limit never triggers.
```

## Why It Happens

1. `[x for x in list if cond]` creates a **new list object** — it's not a view/reference to the original
2. After `_store.pop(key)`, the dict no longer holds any list for that key
3. `window.append(now)` writes to the local variable only
4. On the next call, `defaultdict(list)` creates yet another empty list
5. Net effect: every call sees an empty or single-item window — the rate limiter never fires

## Key Insight

When you filter a dict's list value, the filtered result is a **detached copy**. You must either:
- Always reassign back to the dict (`_store[key] = window`) BEFORE appending
- Or append to `_store[key]` directly instead of the local variable

## Correct Patterns

### Pattern A: Always reassign, prune separately
```python
def check(key: str) -> None:
    now = time.monotonic()
    window = [t for t in _store[key] if now - t < 60]
    _store[key] = window  # ALWAYS reassign — keeps dict and local in sync
    if len(window) >= LIMIT:
        raise RateLimitExceeded
    window.append(now)    # safe: window IS _store[key]

    # Prune stale keys periodically, NOT inline with the check
```

### Pattern B: Mutate in-place (no new list)
```python
def check(key: str) -> None:
    now = time.monotonic()
    entries = _store[key]
    entries[:] = [t for t in entries if now - t < 60]  # in-place slice assignment
    if len(entries) >= LIMIT:
        raise RateLimitExceeded
    entries.append(now)
```

## Related Traps
- `python-mutable-defaults-trap`: default mutable args shared across calls
- `python-async-concurrent-modification-trap`: modifying collections during async iteration

## Detection
- Any code that does `filtered = [x for x in dict[key] if ...]` followed by conditional `dict.pop(key)` and then `filtered.append(...)` — the append is a no-op on the dict.
- Tests that assert rate limiting / sliding window behavior will fail silently (the limiter just never triggers).
