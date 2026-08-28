---
name: local-green-is-not-evidence-when-the-backend-is-gated
description: 스위트가 환경변수/도달성으로 백엔드를 고르면(BSVIBE_DATABASE_URL 있으면 PG 아니면 SQLite, Ollama 안 뜨면 skip), **로컬 전체 통과는 근거가 못 된다.** 가장 값진 테스트가 조용히 skip 되고, 그 skip 은 통과처럼 집계된다. CI 와 로컬이 같은 눈먼 지점을 공유하면 결함은 양쪽 모두를 통과한다. 트리거 - `use_real_pg()`, `pytest.skip("... not reachable")`, "로컬은 되는데 CI 만 실패", "CI 는 green 인데 main 이 깨져 있다", 머지 전 검증 보고.
---

# 백엔드가 게이트되면 "로컬 전부 통과"는 증거가 아니다

## Problem

성숙한 스위트는 값비싼 의존성을 **조건부**로 만든다:

```python
def use_real_pg() -> bool:
    return bool(os.environ.get("BSVIBE_DATABASE_URL")) and can_reach_pg()

if not use_real_pg():
    pytest.skip("real Postgres required — SQLite has no QueuePool to exhaust")
```

- **증상**: `6289 passed` 를 근거로 "검증 완료"라고 보고했는데 CI 가 실패한다.
  더 나쁜 경우: **CI 도 통과했는데 main 이 깨져 있다.**
- **근본 원인**: 스킵된 테스트는 **가장 값진 테스트**다 — 커넥션 풀 고갈, 락 경합,
  벡터 검색, 마이그레이션. 정확히 SQLite 나 mock 이 재현 못 하는 것들이라 조건부가 된 것이다.
  그런데 `passed` 카운트는 스킵을 벌하지 않는다.
- **흔한 오해**: "CI 가 있으니 CI 가 잡아준다."
  → **CI 도 자기 게이트가 있다.** 실측 사례: 한 PR 이 CI green 으로 머지됐는데
  그 PR 이 깬 테스트는 **Ollama 가 필요해 CI 에서 skip** 되고 있었고,
  로컬에서도 마침 Ollama 가 꺼져 있어 **같은 자리에서 skip** 됐다.
  **두 환경이 같은 눈먼 지점을 공유하면 결함은 양쪽을 통과한다.**

## 실측 — 한 PR 에서 세 결함, 전부 SQLite 로컬로는 안 잡힘

| 결함 | 잡은 곳 | SQLite 로컬이 못 잡은 이유 |
|---|---|---|
| 열린 txn 안의 외부 호출 → 커넥션 고갈 | CI(실 PG) | SQLite 엔 고갈시킬 QueuePool 이 없음 |
| 파일이 god-file LOC 임계 초과 | 실 PG 로컬 재현 | (같은 실행에서만 드러남) |
| 이전 PR 이 지식 e2e 를 깼음 | 실 PG **+ Ollama** | CI·로컬 **둘 다** Ollama 없어 skip |

## Solution

1. **머지 전 검증은 CI 동등 환경에서 하라.** 워크플로 파일이 레시피다 —
   서비스 이미지·env·프로비저닝 단계를 그대로 재현한다.
   ```bash
   docker run -d --name citest-pg -e POSTGRES_USER=… -p 5442:5432 pgvector/pgvector:pg16
   export BSVIBE_MIGRATION_DATABASE_URL=…  BSVIBE_DATABASE_URL=…
   uv run alembic upgrade head        # 런타임 롤 프로비저닝까지 겸함
   ```
   ⚠️ 롤을 마이그레이션이 만들어도 **비밀번호가 안 맞을 수 있다** —
   `ALTER ROLE <app_role> WITH PASSWORD '<ci_password>';` 를 한 번 쳐라.
2. **스킵 수를 읽어라.** `6291 passed, 43 skipped` 와 `6333 passed, 1 skipped` 는
   전혀 다른 문장이다. **43 → 1 로 줄었을 때 비로소** 그 스위트가 무엇을 증명하는지 안다.
3. **보고할 때 환경을 함께 말하라.** "전부 통과" 가 아니라
   *"실 PG + Ollama 에서 6333 passed, skip 1(Redis)"*. 환경 없는 통과 수는 의미가 없다.
4. **CI 가 구조적으로 못 도는 테스트를 목록화하라.** 그 목록이 곧
   "머지가 지켜주지 못하는 영역"이고, 사람이 주기적으로 돌려야 하는 것이다.

## Key Insights

- **스킵은 통과가 아니다. 그런데 통과처럼 집계된다.** 이 비대칭이 함정 전체를 만든다.
- **CI 를 최종 방어선으로 믿지 마라 — CI 도 게이트를 갖고 있다.**
  "CI green 인데 main 이 깨졌다"는 거의 항상 *CI 가 그 테스트를 안 돌린* 경우다.
- 조건부 스킵 사유는 **그 테스트가 왜 값진지를 그대로 적어놓는다**
  (*"SQLite has no QueuePool to exhaust"*). 스킵 사유 목록을 읽으면
  **내가 지금 무엇을 증명하지 못했는지** 바로 나온다.
- 다음에 "로컬 전부 통과" 라고 쓰기 직전에: **skip 개수를 세고, 그중 내 변경과
  같은 서브시스템이 있는지 보라.**

---

## 사례 — **벽시계 시간이 두 번째 신호다** (BSVibe 2026-08-28, #844)

이 스킬을 이미 갖고 있었는데도 **같은 세션 안에서 재발했다.** 앞서 세 번은
`BSVIBE_DATABASE_URL` 을 넘겨 제대로 돌렸고, 마지막 결정 실행에서 그걸 빠뜨렸다.

| 실행 | 결과 | 시간 |
|---|---|---|
| 앞선 실행들(PG 붙음) | `6475 passed, **1** skipped` | **607초** |
| 결정 실행(PG 없음) | `6454 passed, **31** skipped` | **305초** |
| 다시(PG 붙음) | `6483 passed, **1** skipped` | 468초 |

`31 passed` 는 초록으로 보였다. 하필 그 PR 이 건드린 게 vault 경로 해석인데
`test_semantic_search_e2e`(note_embeddings)가 스킵된 채였다 — **바꾼 층이 통째로 안 돌았다.**

> **스킵 수와 벽시계 시간은 같은 사실의 두 관측이다.** 스킵 수를 안 읽었어도
> "왜 절반 시간에 끝났지"가 걸렸어야 한다. 값비싼 의존성이 빠지면 **빨라진다.**

**How to apply**
- 같은 스위트의 **직전 실행 시간을 기억하고 비교하라.** 갑자기 빨라졌으면 뭔가 안 돈 것이다.
- 검증 명령을 **환경변수까지 포함해 한 줄로 저장해두고 그걸 재사용하라.**
  손으로 다시 조립하면 이번처럼 빠뜨린다.
- "이 스킬을 안다"는 재발을 막지 못한다. **명령을 기억하는 게 아니라 명령을 보관해야 한다.**

### 곁가지 — 로컬 실패 하나는 `main` 에서 **양성 대조**를 먼저 돌려라

같은 실행에서 `test_rls_is_active_layer3_for_the_runtime_role` 하나가 실패했다.
내 PR 의 회귀로 읽을 뻔했는데, **같은 DB URL 로 `main` 에서 돌리니 동일하게 실패**했다
(최소권한 `bsvibe_app` 이 아니라 superuser 로 붙어서).

로컬 실패를 PR 탓으로 적기 전에 **`main` 워크트리에서 같은 명령 한 번**이 가장 싼 감별이다.
