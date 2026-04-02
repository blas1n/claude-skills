---
name: asyncpg-testing-patterns
description: "asyncpg testing — mock at repository level (preferred) or use @asynccontextmanager for pool/transaction mocking"
version: 1.0.0
triggers:
  - pattern: "testing asyncpg pool.acquire() or conn.transaction() patterns"
---

# asyncpg Testing Patterns

## Strategy: Mock at the Right Level

Mock granularity should be **one level below** the test subject:
- API tests → mock Repository methods
- Service tests → inject AsyncMock repository
- Repository tests → real DB (integration test)

---

## 1. Repository Method Patching (Preferred)

Don't mock pool/connection chains. Patch Repository methods directly:

```python
# ✅ Stable and simple
with patch(
    "myapp.tenant.repository.TenantRepository.get_api_key_by_hash",
    new_callable=AsyncMock,
    return_value=None,
):
    resp = client.get("/api/v1/tenants", headers=headers)
    assert resp.status_code == 401
```

```python
# ❌ Unstable — pool/connection mock chain breaks easily
mock_pool = AsyncMock()
conn = AsyncMock()
mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
conn.fetchrow.return_value = some_record  # doesn't work reliably
```

---

## 2. Transaction Mocking (When Needed)

When testing code that uses `async with pool.acquire() as conn: async with conn.transaction():`, use `@asynccontextmanager`:

```python
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

mock_conn = AsyncMock()
mock_conn.fetchrow = AsyncMock(return_value={"id": uuid4()})

@asynccontextmanager
async def mock_transaction():
    yield

mock_conn.transaction = mock_transaction

@asynccontextmanager
async def mock_acquire():
    yield mock_conn

repo._pool = MagicMock()  # MagicMock, not AsyncMock for pool
repo._pool.acquire = mock_acquire
```

**Key rules**:
- Never use `AsyncMock().return_value` for context managers (returns coroutine, not CM)
- Use `@asynccontextmanager` for every `async with` level
- Use `MagicMock` (not `AsyncMock`) for the pool object
- Assign `conn.transaction` directly (not `.return_value`)

| Anti-Pattern | Error | Fix |
|-------------|-------|-----|
| `pool.acquire.return_value = ctx` | `coroutine does not support async CM` | `@asynccontextmanager` |
| `patch.object(AsyncMock, "acquire")` | `AttributeError` | Patch on instance |
