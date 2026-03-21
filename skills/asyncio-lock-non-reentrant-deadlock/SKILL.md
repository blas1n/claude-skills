---
name: asyncio-lock-non-reentrant-deadlock
description: Python asyncio.Lock is NOT reentrant — adding locks to fix race conditions can introduce deadlocks when a locked method calls another locked method
---

# asyncio.Lock Non-Reentrant Deadlock

## Problem

When fixing race conditions by adding `asyncio.Lock` to write methods, a deadlock occurs if a method that already holds the lock calls another method that also acquires the same lock.

- 증상: Application hangs indefinitely (deadlock) — no error, no crash, just frozen
- 근본 원인: `asyncio.Lock` is NOT reentrant. Unlike `threading.RLock`, acquiring the same lock twice in the same task deadlocks.
- 흔한 오해: "I'll just add `async with self._lock:` to every write method" — this is correct for independent callers, but breaks when locked methods call each other internally.

## Failure Pattern

```python
class Store:
    def __init__(self):
        self._lock = asyncio.Lock()

    async def set_hash(self, path: str, hash: str) -> None:
        async with self._lock:  # Acquires lock
            await self._conn.execute("INSERT ...", (path, hash))
            await self._conn.commit()

    async def rebuild(self) -> None:
        async with self._lock:  # Acquires lock
            await self._delete_all()
            await self._extract_entities()
            await self.set_hash(path, hash)  # ❌ DEADLOCK — lock already held
            await self._conn.commit()
```

## Solution

Use the **public/locked variant pattern**: public method acquires lock and delegates to a `_locked` variant that assumes the lock is already held.

```python
class Store:
    async def set_hash(self, path: str, hash: str) -> None:
        """Public API — acquires lock."""
        async with self._lock:
            await self._set_hash_locked(path, hash)
            await self._conn.commit()

    async def _set_hash_locked(self, path: str, hash: str) -> None:
        """Internal — caller MUST hold _lock."""
        await self._conn.execute("INSERT ...", (path, hash))

    async def rebuild(self) -> None:
        async with self._lock:
            await self._delete_all_locked()
            await self._extract_entities_locked()
            await self._set_hash_locked(path, hash)  # ✓ No deadlock
            await self._conn.commit()
```

### Naming Convention

- Public: `set_hash()`, `delete()`, `upsert()`
- Internal locked: `_set_hash_locked()`, `_delete_locked()`, `_upsert_locked()`

The `_locked` suffix signals "caller must hold the lock" — acts as a contract.

## Key Insights

- `asyncio.Lock` is the async equivalent of `threading.Lock`, NOT `threading.RLock`. There is no async reentrant lock in stdlib.
- The deadlock is silent — no exception, no timeout, just a frozen coroutine. Very hard to debug in production.
- This trap appears specifically when **retrofitting locks onto existing code** to fix race conditions. The original code worked without locks, so internal call chains never considered reentrancy.

## Red Flags

- Adding `async with self._lock:` to multiple methods in the same class
- A locked method calling another public method of the same class
- `rebuild`, `sync`, `migrate` methods that orchestrate multiple write operations — these are prime candidates for deadlock because they call many sub-methods
- Tests pass (because tests rarely exercise the exact concurrent path that triggers deadlock)
- Application "sometimes hangs" in production but works fine in testing

## Checklist: Before Adding asyncio.Lock

1. Map the **call graph** of all methods that will hold the lock
2. Check: does any locked method call another locked method? If yes → use `_locked` variants
3. Keep lock scope minimal — acquire late, release early
4. Never hold a lock across `await` calls to external services (network I/O)
5. Consider whether a snapshot pattern (copy under lock, operate outside) is simpler than locking the entire operation
