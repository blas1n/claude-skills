---
name: python-async-concurrent-modification-trap
description: "Python Async Concurrent Modification Trap — mutable collection modified during iteration in coroutines"
version: 1.0.0
---

# Python Async: Concurrent Modification Trap

**Problem**: In async code, when a mutable list/dict is iterated in one coroutine while another coroutine modifies it, you get `ValueError` during iteration or silent data loss.

**Why it happens**: `async def` functions are concurrent, not parallel. While one coroutine is looping `for item in list`, another coroutine can call `list.remove(item)`, causing:
- `ValueError: list.remove(x): x not in list`
- Silent skipped items (remove shifts indices)
- Memory leaks (failed items never cleaned up)

## Classic Failure Pattern

```python
class WebSocketManager:
    def __init__(self):
        self._connections: list[WebSocket] = []

    async def broadcast(self, message: dict):
        for conn in self._connections:  # ❌ Iterating over mutable list
            try:
                await conn.send_text(json.dumps(message))
            except Exception:
                logger.warning("ws_send_failed")
                # ❌ Failed connection left in list for next broadcast

    def disconnect(self, websocket: WebSocket):
        self._connections.remove(websocket)  # ❌ Can be called during broadcast()

# Usage scenario that causes the bug:
async def main():
    manager = WebSocketManager()

    # Coroutine 1: broadcast running
    await manager.broadcast({"type": "update"})  # ← iterating over _connections

    # Coroutine 2: user disconnects (can happen concurrently)
    manager.disconnect(ws)  # ← modifies _connections during iteration

    # Result: ValueError or skipped items
```

## Solution 1: Snapshot Iteration (MOST COMMON)

```python
class WebSocketManager:
    async def broadcast(self, message: dict):
        # ✓ Iterate over a COPY of the list
        for conn in self._connections[:]:  # [:] creates shallow copy
            try:
                await conn.send_text(json.dumps(message))
            except Exception:
                logger.warning("ws_send_failed")
                # ✓ Safe to remove from original during iteration
                with contextlib.suppress(ValueError):
                    self._connections.remove(conn)
```

**Why it works**: `self._connections[:]` creates a snapshot. Even if the original list is modified, the snapshot doesn't change.

## Solution 2: Lock (WHEN SNAPSHOT ISN'T ENOUGH)

Use when you need to modify AND iterate atomically:

```python
class WebSocketManager:
    def __init__(self):
        self._connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def broadcast(self, message: dict):
        async with self._lock:
            for conn in self._connections:
                try:
                    await conn.send_text(json.dumps(message))
                except Exception:
                    self._connections.remove(conn)

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            with contextlib.suppress(ValueError):
                self._connections.remove(websocket)
```

**Caveat**: Locks can cause deadlocks if not careful. Prefer snapshots.

## Solution 3: Use Thread-Safe Collections

For complex scenarios, use collections designed for concurrent access:

```python
from asyncio import Queue

class WebSocketManager:
    def __init__(self):
        self._connections: asyncio.Queue[WebSocket] = asyncio.Queue()

    async def broadcast(self, message: dict):
        temp_conns = []
        while not self._connections.empty():
            conn = await self._connections.get()
            temp_conns.append(conn)
            try:
                await conn.send_text(json.dumps(message))
            except Exception:
                logger.warning("ws_send_failed")
                # Don't re-add failed connection

        # Restore working connections
        for conn in temp_conns:
            await self._connections.put(conn)
```

## Checklist: Async Mutation Safety

Before writing async code that mutates shared collections:

- [ ] **Iteration + Modification**: Are there async functions that iterate and modify the same list?
- [ ] **Multiple Coroutines**: Can two coroutines run concurrently on the same data?
- [ ] **Snapshot Used**: If iterating, is it over `list[:]` (snapshot)?
- [ ] **Exception Handling**: If catching exceptions during iteration, is removal inside a `contextlib.suppress(ValueError)`?
- [ ] **Tests**: Do concurrent tests exist (asyncio.gather + simultaneous ops)?

## Real-World Examples

### ✅ Good Pattern: Snapshot + Safe Remove
```python
async def broadcast_event(event):
    for subscriber in self._subscribers[:]:  # Snapshot
        try:
            await subscriber.handle(event)
        except UnsubscribedException:
            with contextlib.suppress(ValueError):
                self._subscribers.remove(subscriber)
```

### ❌ Bad Pattern: No Snapshot
```python
async def broadcast_event(event):
    for subscriber in self._subscribers:  # ❌ Direct iteration
        try:
            await subscriber.handle(event)
        except UnsubscribedException:
            self._subscribers.remove(subscriber)  # ❌ Unsafe
```

## Why It's Hard to Detect

The bug only manifests when:
1. Two coroutines run concurrently (timing dependent)
2. One iterates while another modifies
3. Tests often DON'T run truly concurrent tasks

This is why the bug survived until the iterative review caught it!

## Testing Concurrent Modification

```python
@pytest.mark.asyncio
async def test_broadcast_with_concurrent_disconnect():
    """Verify broadcast is safe during concurrent disconnect."""
    manager = WebSocketManager()

    # Add fake connections
    ws1, ws2 = AsyncMock(), AsyncMock()
    manager._connections = [ws1, ws2]

    # Trigger concurrent broadcast + disconnect
    async def disconnect_during_broadcast():
        await asyncio.sleep(0.01)  # Let broadcast start
        manager.disconnect(ws2)     # Disconnect mid-broadcast

    broadcast_task = manager.broadcast({"type": "update"})
    disconnect_task = disconnect_during_broadcast()

    # Should NOT raise ValueError
    await asyncio.gather(broadcast_task, disconnect_task)

    # ws1 should still be in list
    assert ws1 in manager._connections
    # ws2 should be removed
    assert ws2 not in manager._connections
```

## Related Patterns

- **Race condition**: Two tasks read, then write, without synchronization
- **Deadlock**: Two locks wait for each other
- **Memory leak**: Failed items never removed from list (happens in broadcast pattern)
