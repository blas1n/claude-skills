---
name: sqlalchemy-sqlite-pg-compat
description: SQLAlchemy에서 PostgreSQL 전용 기능(partial index, timezone-aware datetime)을 SQLite 테스트 환경과 호환시키는 패턴
---

# SQLAlchemy SQLite-PostgreSQL 테스트 호환성

## Problem

PostgreSQL을 프로덕션 DB로, SQLite를 테스트 DB로 사용할 때 발생하는 호환성 문제들.

- 증상 1: `UNIQUE constraint failed` — partial unique index가 SQLite에서 일반 unique index로 동작
- 증상 2: `TypeError: can't subtract offset-naive and offset-aware datetimes` — SQLite datetime에 tzinfo 없음
- 근본 원인: SQLAlchemy의 `postgresql_where`는 PG 전용이고, SQLite는 `DateTime(timezone=True)`를 무시함
- 흔한 오해: `postgresql_where`가 "모든 DB에서 작동하지 않으면 무시될 것" — 아니다, SQLite에서는 WHERE 없이 일반 unique index가 생성됨

## Solution

### Partial Unique Index

`postgresql_where`와 `sqlite_where`를 동시에 지정 (SQLite는 boolean을 0/1로 저장):

```python
from sqlalchemy import Index, text

Index(
    "uq_one_default_per_tenant",
    "tenant_id",
    unique=True,
    postgresql_where=text("is_default = true"),
    sqlite_where=text("is_default = 1"),  # SQLite: boolean → 0/1
)
```

### Timezone-Aware Datetime 비교

SQLite에서 읽은 datetime은 항상 naive. 비교 전 tzinfo 체크 필수:

```python
from datetime import datetime, timezone

def safe_datetime_diff(dt: datetime) -> float:
    """SQLite-safe datetime subtraction (seconds)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds()
```

### 환경 의존 테스트

로컬 `.env`가 테스트 기대값을 오염하는 경우, 테스트에서 직접 설정을 override:

```python
# BAD: skipif로 환경에 따라 스킵 (로컬에서 실행 불가)
@pytest.mark.skipif(settings.cors_allowed_origins != [], reason="...")

# GOOD: 테스트에서 설정을 명시적으로 override
@pytest.fixture(autouse=True)
def _override_cors(monkeypatch):
    monkeypatch.setattr("backend.src.config.settings.cors_allowed_origins", [])
```

## Key Insights

- `postgresql_where` 없이 `unique=True`만 있으면 SQLite에서 전체 컬럼에 unique 제약이 걸림 — partial index가 아닌 full unique index
- SQLAlchemy `DateTime(timezone=True)`는 PostgreSQL에서만 실제 timezone을 저장. SQLite는 TEXT/REAL로 저장하므로 항상 naive
- 테스트 환경에서 `.env` 파일이 `pydantic-settings`에 의해 자동 로드됨 — `TESTING=1`이어도 override 안 됨

## Red Flags

- SQLite 테스트에서 `IntegrityError: UNIQUE constraint failed`가 partial index 관련 테이블에서 발생
- `TypeError: can't subtract offset-naive and offset-aware datetimes` — DB에서 읽은 datetime 비교 시
- 로컬에서만 실패하는 테스트 — `.env` 파일의 설정값이 테스트 기대값과 충돌
