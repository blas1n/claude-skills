---
name: pgvector-asyncpg-raw-sql-list-bind
description: pgvector 임베딩을 SQLAlchemy raw text() SQL로 바인드할 때 Python list를 그대로 넘기면 asyncpg가 "expected str, got list"로 거부한다. 텍스트형 "[...]" + CAST(:p AS vector) 필요. SQLite 단위테스트로는 못 잡고 실제 PG+실제 임베딩 e2e에서만 표면화.
---

# pgvector + asyncpg: raw SQL list-bind trap

## Problem

pgvector `vector` 컬럼에 임베딩을 저장/검색하는데, SQLAlchemy `text()` raw SQL의
바인드 파라미터로 Python `list[float]`를 그대로 넘기는 경우.

- **증상**: 실제 Postgres에 첫 임베딩이 닿는 순간
  `sqlalchemy.exc.DBAPIError: asyncpg.exceptions.DataError: invalid input for
  query argument $N: [...] (expected str, got list)`. INSERT/SELECT 양쪽 다.
- **근본 원인**: asyncpg에는 pgvector `vector` 타입 codec이 기본 등록돼 있지 않다.
  `text()` 바인드는 SQLAlchemy 타입 시스템을 우회해 값이 asyncpg로 직행하므로,
  list를 vector로 인코딩할 방법이 없어 거부된다. (ORM 컬럼타입
  `pgvector.sqlalchemy.Vector` / 커스텀 `EmbeddingVector` TypeDecorator를 쓰면
  SQLAlchemy가 인코딩해주지만, raw SQL은 그 경로를 안 탄다.)
- **흔한 오해**: 단위테스트(SQLite + fake embedder)가 전부 green이라 안전하다고 믿음.
  SQLite엔 `vector` 타입도 `<=>`도 없어서 PG 전용 경로 자체가 절대 실행되지 않고,
  fake embedder는 종종 list를 store 안 하거나 InMemory 백엔드만 친다 → 버그가
  실제 PG + 실제 임베딩에서만 처음 터진다.

## Solution

raw SQL에서는 임베딩을 pgvector **텍스트 표현** `'[v1,v2,...]'`로 인코딩하고
`CAST(:param AS vector)`로 캐스팅한다. store(INSERT)와 search(`<=>` 쿼리) 양쪽 모두.

```python
def _to_pgvector(embedding: list[float]) -> str:
    # pgvector text input form; CAST(... AS vector)와 함께 사용
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"

# store
await session.execute(
    text("INSERT INTO note_embeddings (..., embedding, ...) "
         "VALUES (..., CAST(:emb AS vector), ...)"),
    {"emb": _to_pgvector(vec), ...},
)

# search
await session.execute(
    text("SELECT note_path, embedding <=> CAST(:qv AS vector) AS distance "
         "FROM note_embeddings WHERE ... ORDER BY embedding <=> CAST(:qv AS vector) LIMIT :lim"),
    {"qv": _to_pgvector(query_vec), ...},
)
```

대안: `pgvector.asyncpg.register_vector(conn)`로 codec 등록 — 단 SQLAlchemy 풀링
+ 비동기 연결 라이프사이클과 엮으면 번거로워 raw text() 경로에선 text+CAST가 더 단순.
write를 ORM 모델(EmbeddingVector 컬럼)로 하고 `<=>` 검색만 raw로 하는 혼합도 가능.

## Key Insights

- **ORM 컬럼타입은 인코딩해주지만 raw `text()`는 우회한다.** pgvector를 raw SQL로
  만질 거면 list를 절대 그대로 바인드하지 말고 text+CAST로 변환하라. (같은 코드베이스의
  `EmbeddingVector` TypeDecorator가 ORM에선 잘 돌기 때문에 raw 경로에서 방심하기 쉽다.)
- **PG 전용 경로는 SQLite 게이트 테스트로 결코 못 막는다.** `vector`/`<=>`가 없는
  SQLite에선 그 코드가 실행조차 안 된다. 실제 PG(+가능하면 실제 임베딩 제공자)로 도는
  e2e/smoke 테스트가 유일한 안전망이다.
- **버그는 패턴 단위로 번진다.** 한 백엔드에서 list-bind를 발견하면 같은 패턴을 복붙한
  sibling(예: 또 다른 `storage/pg.py`)도 같은 latent 버그를 갖는다. 미배선이라 안 터졌을 뿐.
  하나 고칠 때 형제들도 grep해서 함께 점검/수정 여부를 판단하라.

## Red Flags

- SQLAlchemy `text()` 안에 `CAST(:x AS vector)` 또는 `<=>`가 있는데 바인드 값이 `list`.
- 단위테스트는 전부 통과하는데 첫 prod/실DB 호출에서 `DataError: expected str, got list`.
- "InMemory 백엔드 + fake embedder로만 검증했다"는 PG 전용 벡터 코드.
- pgvector 마이그레이션은 fresh-PG 테스트로 검증되지만 store/search **쿼리**는 PG에서
  한 번도 안 돌려본 상태.
