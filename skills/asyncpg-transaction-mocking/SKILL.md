---
name: asyncpg-transaction-mocking
description: How to mock nested asyncpg pool.acquire() + conn.transaction() async context managers in pytest. Use when mocking asyncpg connection pool and transactions in tests, especially when code uses `async with pool.acquire() as conn: async with conn.transaction():`
---

# asyncpg Transaction Mocking

## Problem

When production code uses nested async context managers:

```python
async with self._pool.acquire() as conn:
    async with conn.transaction():
        await conn.fetchrow(...)
```

Standard `AsyncMock` chaining **does not work** for mocking this pattern:

```python
# WRONG - causes "coroutine object does not support async context manager"
repo._pool = AsyncMock()
repo._pool.acquire.return_value = mock_ctx  # Broken!
```

`AsyncMock().method.return_value` returns a coroutine, not an async context manager. The `__aenter__`/`__aexit__` protocol is not satisfied.

## Solution

Use `@asynccontextmanager` to build proper async context manager mocks:

```python
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

# 1. Create the mock connection with desired return values
mock_conn = AsyncMock()
mock_conn.fetchrow = AsyncMock(return_value={"id": uuid4(), ...})

# 2. Create transaction context manager
@asynccontextmanager
async def mock_transaction():
    yield

mock_conn.transaction = mock_transaction

# 3. Create acquire context manager
@asynccontextmanager
async def mock_acquire():
    yield mock_conn

# 4. Assign to pool (use MagicMock, not AsyncMock for the pool)
repo._pool = MagicMock()
repo._pool.acquire = mock_acquire

# 5. For SQL loader, use a simple MagicMock
repo._sql = MagicMock()
repo._sql.query = lambda name: f"-- mock: {name}"
```

## Key Rules

1. **Never use `AsyncMock().return_value` for context managers** — it returns a coroutine, not a CM
2. **Use `@asynccontextmanager`** for every `async with` level (acquire, transaction)
3. **Use `MagicMock` (not `AsyncMock`) for the pool object** — `acquire` is assigned as a function, not an async attribute
4. **`conn.transaction` is assigned directly** (not `.return_value`) because it's called as `conn.transaction()` yielding a CM

## Anti-Patterns

| Pattern | Error | Fix |
|---------|-------|-----|
| `pool.acquire.return_value = ctx_mock` | `coroutine does not support async CM` | Use `@asynccontextmanager` |
| `patch.object(AsyncMock, "acquire", ...)` | `AttributeError: class has no attribute` | Patch on the instance, not the class |
| `mock_ctx.__aenter__ = AsyncMock(return_value=conn)` | Works for 1 level but fragile for nesting | Prefer `@asynccontextmanager` |

## When to Apply

- Refactoring code from individual repo method calls to raw `conn.fetchrow()` inside transactions
- Any test that mocks `asyncpg.Pool.acquire()` + `conn.transaction()`
- PresetService, batch operations, or any multi-step DB writes wrapped in transactions
