---
name: a-globally-set-experiment-condition-is-neither-private-nor-durable
description: 공유 상태(DB 정책·전역 설정·스키마)를 바꿔 실험 조건을 만들면, 그 조건은 (1) 측정 대상이 되돌릴 수 있고 (2) 옆 테스트로 샌다. 런 전에만 확인하면 무효인 회차를 진짜 숫자로 보고하게 된다.
version: 1.0.0
task_types: [debugging, evaluation, testing]
triggers:
  - pattern: "RLS 정책 / feature flag / 전역 설정을 바꾸고 테스트 스위트를 돌려 '무엇이 깨지나' 측정"
  - pattern: "DROP/CREATE POLICY · ALTER TABLE · SET GLOBAL 을 테스트나 프로브 안에서 실행"
  - pattern: "'수정 전 N failed → 수정 후 0 failed' 처럼 기대보다 좋은 숫자가 나왔을 때"
  - pattern: "단독 실행은 통과, 다른 테스트와 묶으면 간헐 실패"
category: trap
---

# 전역으로 건 실험 조건은 사적이지도, 지속되지도 않는다

## Problem

*"조건 X 로 바꾸면 무엇이 깨지나"* 를 재려면 공유 상태를 건드리게 된다 — DB 정책,
스키마, 전역 설정. 그런데 그 조건은 **두 방향으로 샌다.**

| 방향 | 증상 |
|---|---|
| **측정 대상이 조건을 되돌린다** | 스위트 안의 어떤 테스트가 마이그레이션·부트스트랩을 돌려 내가 건 조건을 원복시킨다. 런은 조건 A 로 시작해 조건 B 로 끝난다 |
| **조건이 옆으로 샌다** | DDL 은 ACCESS EXCLUSIVE 락이다. 공유 DB 런 한가운데서 치면 이웃 테스트가 **간헐적으로** 깨지고, 그 실패는 *내 제품 변경의 회귀*처럼 보인다 |

**근본 원인**: 실험 조건을 *프로세스 밖*(공유 자원)에 두었는데, 측정도 그 자원 위에서
돈다. 조건과 피험자가 같은 그릇에 있다.

**흔한 오해**: "런 전에 조건을 확인했으니 이 회차는 유효하다." — 런 **후**에 다시
확인하기 전까지는 모른다.

## 2026-09-28 실측 (BSVibe, PG RLS)

`USING (GUC IS NULL OR GUC='' OR col=GUC)` 의 빈-GUC 탈출구를 제거해 fail-closed 를
만들고 *"무엇이 깨지나"* 를 쟀다. **두 회차가 무효였다.**

1. `psql ... >/dev/null 2>&1` 이 **DDL 에러를 가렸다** → 정책이 안 바뀐 채로 측정.
   다시 읽어 보니 여섯 표 중 일부가 여전히 fail-open
2. `tests/data/test_rls_pg.py` 가 **마이그레이션을 돌려 정책을 원복**시켰다 →
   런 전 6/6 fail-closed, **런 후 0/6**

2번 회차의 결과가 *"20 failed → 0 failed"* 였다. **보고 직전이었다.**

⭐ 그리고 같은 세션에서 반대 방향도 겪었다: 내 테스트가 `DROP/CREATE POLICY` 로
fail-closed 를 만들자 **다른 테스트 2건이 간헐 실패**했다. 재실행하니 통과 —
내가 만든 flake 인데 **내 제품 변경의 회귀로 오진할 뻔했다.**

## Solution

### 1. 조건을 **런 전후로** 재라 — 세는 쿼리를 따로 두어라

```bash
closed_count () {  # 조건 자체를 세는 쿼리. 설정 명령의 성공 여부를 믿지 않는다.
  psql -t -A -c "select count(*) from pg_policies
                 where policyname='rls_workspace_isolation' and qual not like '%IS NULL%';"
}
flip_closed; echo "런 전: $(closed_count)/6"
pytest <subset>
echo "런 후: $(closed_count)/6"   # ← 6 이 아니면 이 회차는 버린다
```

### 2. 설정 단계의 출력을 **가리지 마라**

`>/dev/null 2>&1` 은 조건을 만드는 명령에 절대 쓰지 마라. 최소한
`-v ON_ERROR_STOP=1` 을 주고, 실패하면 거기서 멈춰라.

### 3. 조건을 **세션/트랜잭션 범위로** 만들 길을 먼저 찾아라

전역 DDL 대신 같은 명제를 사적 상태로 만들 수 있는 경우가 많다.

| 하고 싶은 것 | 전역(나쁨) | 사적(좋음) |
|---|---|---|
| "GUC 가 안 맞으면 쓰기가 막힌다" | 정책에서 탈출구 제거 | **남의 id 를 GUC 에 박는다**(`set_config(..., is_local=true)`) — 탈출구는 *비어 있음* 에만 열리므로 비어 있지 않은 값은 오늘 정책으로도 막힌다 |
| "이 플래그가 꺼지면" | 전역 설정 변경 | 그 코드가 읽는 자리를 monkeypatch |

사적 조건은 **락을 안 잡고**, 옆 테스트로 안 새고, 런 후 원복을 검증할 필요도 없다.

### 4. 좋은 숫자가 나온 순간이 대조군을 다시 볼 시점이다

나쁜 숫자는 의심하지만 **좋은 숫자는 안 의심한다**. *"수정 하나로 20건이 전부
풀렸다"* 같은 결과가 나오면, 기뻐하기 전에 조건부터 다시 재라.

### 5. 간헐 실패를 내 변경 탓으로 돌리기 전에 — **재현**하라

단독 통과 + 묶으면 실패 = 순서/공유 상태. 그리고 **내가 방금 추가한 테스트가
용의자**일 수 있다. 내 테스트를 빼고 같은 조합을 돌려 보면 1분이면 갈린다.

## Verification

- [ ] 조건을 세는 쿼리가 **설정 명령과 별개**로 존재하는가
- [ ] 런 **후**에도 그 값을 확인했는가
- [ ] 설정 단계가 실패하면 **시끄럽게** 죽는가(`ON_ERROR_STOP` / 출력 미차단)
- [ ] 같은 명제를 세션 범위로 만들 길을 찾아봤는가
- [ ] 새 테스트를 넣은 뒤 **그것만 빼고** 같은 조합을 한 번 돌려 봤는가

## Related

- `absence-measurement-validity-check` — 0 을 세기 전에 생산자가 도는지 확인
- `a-check-that-cannot-flip-is-not-measuring-anything` — 한쪽 판정만 낼 수 있는 검사
- `ci-flake-reproduce-before-rerunning` — 재실행 전에 재현
