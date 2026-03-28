---
name: asyncpg-repository-testing
description: "asyncpg Repository Testing with AsyncMock — mocking pool.acquire() chain for unit tests"
version: 1.0.0
---

# asyncpg Repository Testing with AsyncMock

## Problem

asyncpg의 `pool.acquire()` → async context manager → `conn.fetchrow()` 체인을
`AsyncMock`으로 모킹할 때, context manager 설정이 복잡하고 불안정하다.

특히 Repository 패턴 (`async with self._pool.acquire() as conn:`) 에서:
- `AsyncMock()`의 자동 context manager는 내부 메서드 호출 시 예측 불가능한 결과
- `conn.fetchrow()` 등의 반환값을 제어하기 어려움
- 에러 케이스에서 500 대신 기대한 4xx 응답을 받지 못함

## Solution: Repository 메서드 레벨에서 patch

pool/connection을 mock하지 말고, **Repository 메서드 자체를 patch**하는 것이 안정적:

```python
# BAD: pool + connection mock 체인 (불안정)
mock_pool = AsyncMock()
conn = AsyncMock()
mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
conn.fetchrow.return_value = some_record  # 이게 제대로 안 먹힘

# GOOD: Repository 메서드 직접 patch (안정적)
with patch(
    "myapp.tenant.repository.TenantRepository.get_api_key_by_hash",
    new_callable=AsyncMock,
    return_value=None,  # or some_record
):
    resp = client.get("/api/v1/tenants", headers=headers)
    assert resp.status_code == 401
```

## When to Use

- FastAPI + asyncpg + Repository 패턴 테스트 시
- `pool.acquire()` as context manager를 사용하는 코드 테스트 시
- 특히 FastAPI TestClient (sync) 에서 async repository를 호출하는 경우

## Key Insight

**mock의 granularity는 테스트 대상의 한 단계 아래**가 적절:
- API 테스트 → Repository 메서드를 mock
- Service 테스트 → Repository 인스턴스를 AsyncMock()으로 주입
- Repository 테스트 → 실제 DB 필요 (integration test)

pool/connection 수준의 mock은 너무 low-level이라 context manager 설정 지옥에 빠진다.

## Origin

BSGateway 멀티테넌트 Phase 1에서 발견. `test_invalid_auth_returns_401`이 500을 반환 —
mock_pool의 acquire context manager가 repository 내부에서 올바르게 동작하지 않았음.
Repository 메서드 레벨 patch로 전환하여 해결.
