---
name: verification-query-moves-the-metric
description: 배선이 도달했는지 재려고 잡은 지표를, 확인하는 쿼리 자체가 움직이는 경우 — `pg_stat_user_tables.seq_scan` 을 지표로 쓰면 `count(*)` 확인이 카운터를 올려 거짓 양성이 된다. 기준선을 문서로 넘겨받으면 다음 세션이 자기 확인 쿼리를 성공으로 오독한다. 트리거 - "카운터가 늘었으면 배선된 것", 스캔/히트 카운터를 증거로 삼기, 기준선을 인수인계에 적기, 관측 지표 설계.
version: 1.0.0
task_types: [debugging, evaluation, design]
triggers:
  - pattern: "'이 값이 늘었으면 코드가 실제로 돌았다'는 형태의 실증 계획"
  - pattern: "pg_stat / 캐시 히트 / 액세스 카운터를 배선 증거로 사용"
  - pattern: "인수인계 문서에 지표 기준선을 적어 다음 세션에 넘길 때"
category: trap
---

# 확인하는 행위가 지표를 움직인다

## Problem

"이 코드가 실제로 프로덕션에서 돌기 시작했나"를 재려고 **읽기 카운터**를 지표로 잡는다.
그런데 **확인 쿼리가 그 카운터를 올린다.**

BSVibe 실측 (2026-08-20). 전임 세션이 인수인계에 이렇게 적었다:

> 검증법: `note_embeddings` 의 스캔 카운터 델타.
> **기준선: `seq_scan=196, idx_scan=40`.** 다음 settle 이후 다시 재서 늘었으면
> 컴파일러가 실제로 볼트를 읽은 것이다.

다음 세션이 확인해보니 **197** 이었다. "늘었다 → 배선 성공"으로 읽힐 자리였다.
대조 실험:

```
읽기만(select seq_scan …):        198
select count(*) from note_embeddings   ← 이게 곧 seq scan
읽기만 다시:                       199
```

`count(*)` 한 번이 카운터를 **1** 올린다. 196→199 의 증가분은 **전부 확인 쿼리 자신**이었고
실제 settle 은 **0회**였다. `idx_scan` 은 40 그대로.

- 증상: 지표가 "조금씩" 오른다. 프로듀서 로그·행 생성 같은 다른 증거는 하나도 없다.
- 근본 원인: 관측 대상과 관측 도구가 **같은 통계 카운터를 공유**한다.
- 흔한 오해: "읽기 카운터는 프로덕션 코드가 읽을 때만 오른다" — psql 도 클라이언트다.

## Solution

### 1. 관측이 건드리지 않는 축을 골라라

| 나쁨 | 좋음 |
|---|---|
| `seq_scan` (모든 `count(*)` 가 올린다) | 프로듀서가 남기는 **구조화 로그** (`ingest_compile_batch_complete`) |
| 캐시 히트 카운터 | 그 경로가 만드는 **행의 존재** (`activity_type='settle'`) |
| "테이블이 읽혔나" | "그 읽기가 만들어낸 **산출물**이 있나" |

**원칙: 읽기가 아니라 쓰기를 세라.** 쓰기는 확인 쿼리가 만들 수 없다.

### 2. 그래도 카운터를 쓴다면 확인 SQL 에 `count(*)` 를 넣지 마라

```sql
-- 나쁨: 한 문장 안에서 지표를 오염시킨다
select (select count(*) from t)||' rows, seq='||seq_scan from pg_stat_user_tables …;
-- 좋음
select seq_scan, idx_scan from pg_stat_user_tables where relname='t';
```

### 3. 기준선을 인수인계에 적을 때는 **오염 조건을 함께** 적어라

기준선 숫자만 넘기면 다음 세션은 그 숫자를 신뢰한다. 지표가 어떻게 오염되는지를 같이 적지
않으면 **문서가 거짓 양성을 만들어낸다.**

```markdown
-- 오염 없이 읽기 (count(*) 를 절대 같이 치지 마라)
select seq_scan, idx_scan from pg_stat_user_tables where relname='note_embeddings';
-- 기준선: idx_scan = 40  ← 이쪽을 봐라. seq_scan 은 측정으로 오른다.
```

### 4. 델타가 작으면 먼저 자기 자신을 의심하라

배선이 도달했다면 보통 **한 자릿수가 아니다**. `+1`, `+3` 처럼 확인 횟수와 비슷한 델타는
관측자 효과부터 배제해라 — 대조 실험이 30초면 끝난다:

```bash
읽기만 → 값 기록 → 확인 쿼리 한 번 → 읽기만 → 값 비교
```

## Verification

- [ ] 확인 쿼리를 N번 반복했을 때 지표가 N만큼 오르지 **않는다**
- [ ] 지표 상승이 프로듀서 측 증거(로그·행)와 **함께** 나타난다
- [ ] 인수인계에 적은 기준선에 "이렇게 재라 / 이건 오염된다"가 붙어 있다

## Related

- `absence-measurement-validity-check` — 반대 방향: 0을 쟀는데 프로듀서가 꺼져 있던 경우
- `activity-recording-drift-invalidates-historical-counts` — 과거 카운트가 기록 방식 변경으로 무효
- `acceptance-gate-must-measure-delta-not-state` — 게이트는 상태가 아니라 델타를 재야 한다
