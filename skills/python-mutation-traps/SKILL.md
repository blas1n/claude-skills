---
name: python-mutation-traps
description: "Python data mutation traps — mutable defaults, dict reference detach, async concurrent modification"
version: 1.0.0
triggers:
  - pattern: "code uses module-level mutable defaults, dict filtering with pop, or async iteration over shared collections"
---

# Python Data Mutation Traps

## 1. Mutable Defaults (Shallow Copy Trap)

`dict()`, `list()`, `.copy()`, `{**d}` only perform **shallow copies**. Nested mutable objects remain shared references.

```python
# BUG: nested dicts are shared references
_DEFAULTS = {"entity_types": {"note": {}, "person": {}}}

def get_config():
    return dict(_DEFAULTS)  # SHALLOW copy only!

a = get_config()
a["entity_types"]["food"] = {}  # Mutates _DEFAULTS too!
```

**Fix**: Always use `copy.deepcopy()` for nested mutable structures.

**Detection**: Module-level `dict`/`list` with nested mutables + copied with `dict()`/`.copy()` + nested values mutated after copying.

---

## 2. Dict Reference Detach Trap

List comprehension filtering creates a **new list**, not a view. If you pop the dict key then append to the filtered list, the append is a no-op on the dict.

```python
_store: dict[str, list[float]] = defaultdict(list)

def check(key: str) -> None:
    now = time.monotonic()
    window = [t for t in _store[key] if now - t < 60]  # NEW list, detached
    if not window:
        _store.pop(key, None)  # key removed
    else:
        _store[key] = window
    window.append(now)  # ← appends to orphaned local list, NOT dict
```

**Fix**: Always reassign back before appending, or mutate in-place with slice assignment:

```python
entries = _store[key]
entries[:] = [t for t in entries if now - t < 60]  # in-place
entries.append(now)  # safe
```

---

## 3. Async Concurrent Modification

In async code, iterating a mutable list in one coroutine while another modifies it causes `ValueError` or silent data loss.

```python
async def broadcast(self, message: dict):
    for conn in self._connections:  # ❌ Direct iteration
        await conn.send_text(json.dumps(message))
    # Another coroutine calls self._connections.remove(ws) concurrently → crash
```

**Fix**: Snapshot iteration with `list[:]`:

```python
async def broadcast(self, message: dict):
    for conn in self._connections[:]:  # ✓ Snapshot copy
        try:
            await conn.send_text(json.dumps(message))
        except Exception:
            with contextlib.suppress(ValueError):
                self._connections.remove(conn)
```

**Checklist**:
- [ ] Are there async functions that iterate and modify the same collection?
- [ ] Can two coroutines run concurrently on the same data?
- [ ] Is iteration over `list[:]` (snapshot)?
- [ ] Is removal inside `contextlib.suppress(ValueError)`?

---

## Related

- YAML `safe_load` auto-parses dates → compare with `str(value)`
- Sync→async refactor: change `MagicMock` to `AsyncMock` for awaited methods
