---
name: limit-before-filter-starves-a-queue
description: 큐 claim 이 SQL 에서 "오래된 순 N 개"를 가져온 뒤 Python 에서 영구히 처리되지 않을 행(거절·보류 표시)을 건너뛰면, 그 행들이 창을 영원히 차지한다 — N 개가 쌓이는 순간 큐는 새 행을 다시는 보지 못한다. 조용하다: 에러도 로그도 없이 그냥 아무것도 안 들어온다. 트리거 - SELECT … ORDER BY … LIMIT 뒤에 in-process `continue`, "JSON 키 판정이 DB 마다 달라서 Python 에서 거른다" 주석, 새 상태 표시(held/parked/skipped)를 큐 행에 추가할 때, 큐가 갑자기 멈췄는데 에러가 없을 때.
---

# LIMIT 뒤에 거르면 큐가 굶는다

## Problem

```python
rows = select(Trigger).where(~has_request).order_by(received_at).limit(50)
for r in rows:
    if r.payload.get("_received_filtered"):   # 거절된 행 — Request 가 영원히 안 생긴다
        continue
```

거절된 행은 "아직 처리 안 됨" 조건(`~has_request`)을 영원히 만족한다. 오래된 순이라 항상 창 앞에 있다.
50 개가 쌓이면 창 전체가 거절분이고, 새 트리거는 51 번째라 영영 안 보인다. bsvibe 인테이크(2026-10-06)는
일시정지 PR 마다 하나씩 쌓이고 있었다 — Direct 제출까지 같은 큐라 전부 멈췄을 것이다.

새 "보류" 표시를 추가하면 같은 구멍이 커진다.

## Solution

- 영구 표시는 **SQL 에서, LIMIT 전에** 뺀다. JSON 키 판정이 걱정이면 SQLAlchemy 의
  `Row.payload[KEY].as_string().is_(None)` — PG `->>` / SQLite `json_extract` 둘 다 "키 없음 = NULL"
- 둘 다에서 확인: 일회용 PG 컨테이너(pgvector 면 `CREATE EXTENSION vector` 먼저)
- 테스트: `batch_size=3`, 표시된 행 3 개(더 오래됨) + 새 행 1 개 → 새 행이 처리되는가. 수정 전 RED 여야 한다
- 보류 행은 따로 "풀어주는" 경로가 필요하다(표시 제거 → 다음 claim 에 들어온다). 보류 행이 다른 테넌트를
  굶기지 않는지도 테스트

## Key Insights

- "처리 안 됨" 의 정의에 "영원히 처리 안 될 것"이 섞이면 큐는 언젠가 반드시 멈춘다
- in-process 필터는 LIMIT 이 없을 때만 무해하다
