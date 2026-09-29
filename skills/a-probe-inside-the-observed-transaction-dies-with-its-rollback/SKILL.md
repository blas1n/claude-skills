---
name: a-probe-inside-the-observed-transaction-dies-with-its-rollback
description: DB 안에 심은 측정 프로브(정책 함수·트리거·감사 함수)가 기록을 **표에 INSERT** 하면, 그 INSERT 는 관측 대상과 같은 트랜잭션에 묶여 대상이 롤백될 때 같이 사라진다. 그리고 ORM 의 읽기 전용 세션은 닫힐 때 기본으로 rollback 한다 — 그래서 「읽기」가 통째로 측정에서 빠지고, 결과는 「0」이라는 좋은 소식처럼 보인다. 기록은 트랜잭션 밖 채널(RAISE LOG · NOTICE · dblink)로, 대조군은 롤백되는 세션에 걸어라.
version: 1.0.0
task_types: [debugging, evaluation, security]
triggers:
  - pattern: "RLS 정책·트리거·SECURITY DEFINER 함수로 질의를 기록하는 프로브"
  - pattern: "감사/계측 로그 표에 INSERT 하는 DB 함수"
  - pattern: "측정 결과가 0 이어서 '문제 없음'으로 읽으려는 순간"
  - pattern: "SQLAlchemy/ORM 세션이 commit 없이 닫히는 읽기 경로를 세야 할 때"
category: trap
---

# 관측 대상의 트랜잭션 안에 사는 프로브는 그 롤백과 함께 죽는다

## 무엇이 일어났나 (BSVibe #959, 2026-09-29)

RLS 정책에 `rls_probe(t)` 를 붙였다 — GUC 가 비어 있으면 `current_query()` 를 `rls_probe_log` 표에
INSERT 하고 `true` 를 돌려주는(판정은 안 바꾸는) SECURITY DEFINER 함수. 전체 스위트를 돌리고 로그를 셌다.

* production 계층(실제 인증 경로) 블라인드 **0** → 「API/MCP 는 닫혔다」로 읽힐 뻔했다
* 그런데 **반드시 찍혀야 할** 테스트 헬퍼의 블라인드 조회(GUC 없이 `select … from execution_runs`)도 **0**
* 원인: 헬퍼는 `async with factory() as session:` 으로 읽고 **commit 없이** 닫았다 → SQLAlchemy 가 rollback →
  프로브가 그 트랜잭션 안에서 한 INSERT 도 같이 롤백
* `RAISE LOG` 로 바꾸자 6337 → **7260**. 약 920건이 사라지고 있었고, 그 결함 아래서 만든 「11곳」 목록은
  **커밋된 트랜잭션의 블라인드만** 센 것이었다. 새로 3곳(웹훅 경로)이 나왔다

## 왜 잘 안 보이나

* 쓰기 경로는 대부분 commit 하므로 **쓰기는 잘 잡힌다** — 장치가 「동작한다」는 인상을 준다
* 빠지는 건 **읽기 전용** 세션이고, 빠진 결과는 0 = 「문제 없음」과 구분이 안 된다
* 대조군을 psql 한 줄로 걸면 autocommit 이라 **통과한다** — 롤백 경로를 안 밟는다

## 할 일

1. **기록 채널을 트랜잭션 밖으로.** Postgres: `RAISE LOG 'TAG|%|%', t, current_query()` → 서버 로그
   (`docker logs --since <T0>` 로 수거). `log_min_messages` 기본값(WARNING)에서도 LOG 는 나온다.
   대안: `dblink` 자율 트랜잭션, `pg_notify`(단 NOTIFY 도 트랜잭션 커밋 때 전달 — **안 된다**)
2. **대조군을 롤백되는 세션에.** `BEGIN; <블라인드 SELECT>; ROLLBACK;` 이 기록되는지. autocommit 대조군은 이 결함을 못 잡는다
3. **결과 집합 안의 양성 대조군.** 「0」을 보고하기 전에, 코퍼스 안에서 **반드시 있어야 할 한 건**을 먼저 찾아라.
   그게 0 이면 숫자 전체를 버려라
4. 정책식은 **행마다** 평가된다 — 빈 표에 대한 SELECT 는 프로브를 안 부른다. 대조군엔 행을 하나 넣고

## 같은 모양

* 계측 카운터를 **같은 트랜잭션**에서 `ON CONFLICT DO UPDATE` → 행 락 경합으로 교착(09-28). 계측은 경합 없고 트랜잭션 없는 채널로
* 애플리케이션 감사 로그를 요청 트랜잭션과 같이 커밋 → **실패한 요청**(롤백)의 감사가 사라진다. 실패야말로 남아야 할 기록이다

관련: [[absence-measurement-validity-check]] (생산자가 꺼져 0) · [[a-check-that-cannot-flip-is-not-measuring-anything]] (반대 판정을 한 번 강제로 보라)
