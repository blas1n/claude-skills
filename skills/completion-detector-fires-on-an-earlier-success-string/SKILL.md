---
name: completion-detector-fires-on-an-earlier-success-string
description: 긴 작업을 기다리는 폴링 루프의 패턴이 **종료 이벤트에만** 나타나는 문자열이 아니면, 앞선 단계의 성공 메시지에 걸려 일찍 끝난다 — "끝났다"는 알림이 오는데 결과는 아직 없다. 체인된 게이트(`ruff && mypy && pytest`)에서 특히 잘 터진다. 종료 신호는 **형태로 유일**해야 하고, 안 되면 마커를 직접 심어라. 트리거 - `until grep -q ...` 대기, `tail -f | grep` 완료 감지, CI/배포 폴링, 여러 도구를 && 로 묶은 게이트.
version: 1.0.0
task_types: [devops, testing, workflow]
triggers:
  - pattern: "until grep -q \"passed|failed\" ... 처럼 로그를 폴링해 완료를 감지할 때"
  - pattern: "여러 명령을 && 로 묶어 한 파일에 출력하고 그 파일을 감시할 때"
  - pattern: "완료 알림이 왔는데 결과가 비어 있을 때"
category: trap
---

# 완료 감지기가 앞 단계의 성공 문자열에 걸린다

## Problem

긴 스위트를 백그라운드로 돌리고 결과를 기다린다:

```bash
uv run ruff check . && uv run mypy . && uv run pytest -q > out.log 2>&1 &

# 결과가 나오면 알려줘
until grep -qE "passed|failed" out.log; do sleep 10; done
tail -14 out.log
```

**즉시 끝난다.** `ruff` 가 먼저 `All checks passed!` 를 찍기 때문이다.
`pytest` 는 아직 10분 남았는데 대기 루프는 "완료"를 신고하고, `tail` 은
아직 `=== PYTEST ===` 헤더만 있는 파일을 보여준다.

BSVibe 2026-08-28 실측. 위 루프가 정확히 이렇게 헛돌았고, 나는 알림을 받고
결과 파일을 열었다가 pytest 요약이 없다는 걸 보고서야 알아챘다.

> **종료 신호로 고른 문자열이 앞 단계에도 나타나면, 그 감지기는 도착하지 않은 결과를
> 도착했다고 읽는다.** 침묵이 성공이 아니듯, **소음도 성공이 아니다.**

### 왜 잘 안 보이나

- 패턴을 **관대하게** 잡는 것이 안전해 보인다 — `passed|failed|error` 는 실패까지
  잡으려는 좋은 의도였다. 넓힐수록 오작동 확률이 **올라간다**.
- 게이트를 `&&` 로 묶는 습관 때문에 한 파일에 **여러 도구의 요약**이 섞인다.
- 거짓 완료는 **에러가 아니다.** 명령은 exit 0 이고 알림도 정상이다.
  유일한 증상은 "결과가 이상하게 비어 있다"인데, 그건 작업이 실패한 것처럼도 보인다.

## Solution

### 1. 종료 신호는 **형태로 유일**해야 한다

pytest 요약에는 **숫자가 앞에 붙는다**. ruff 의 `All checks passed!` 에는 없다.

```bash
until grep -qE "[0-9]+ (passed|failed|error)" out.log; do sleep 15; done
```

고를 때 물어라: **이 정규식이 앞 단계 출력 어디에도 안 나타난다고 말할 수 있나?**
말 못 하면 그 패턴이 아니다.

### 2. 확신이 안 서면 **마커를 직접 심어라**

추측할 필요가 없다. 끝에 내가 아는 문자열을 찍는다.

```bash
{ uv run ruff check . && uv run mypy . && uv run pytest -q; echo "__GATE_DONE__ rc=$?"; } > out.log 2>&1 &
until grep -q "__GATE_DONE__" out.log; do sleep 15; done
```

rc 까지 같이 실으면 **완료와 성패를 한 번에** 읽는다.
(⚠️ 파이프로 넘기면 exit code 가 마지막 명령 것이 된다 → [[piped-gate-masks-exit-code]])

### 3. 애초에 **프로세스 종료**를 기다려라

로그 파싱은 프로세스 종료를 관측할 수 없을 때만 쓰는 대체 수단이다.
백그라운드 태스크가 완료 알림을 주는 환경이면 **그 알림을 기다려라.**
폴링 루프를 하나 더 얹으면 신호원이 둘이 되고, 둘 중 약한 쪽이 먼저 거짓말한다.

### 4. 실패도 잡히는지 확인하라

완료 패턴을 좁히다가 **실패 종료를 못 잡게** 되면 크래시에서 영원히 매달린다.
좁힌 뒤 반드시 반대편을 확인:

| 종료 형태 | 내 패턴이 잡나 |
|---|---|
| 전부 통과 | `123 passed` ✅ |
| 실패 있음 | `2 failed, 121 passed` ✅ |
| 수집 에러 | `error` / `ERROR` — 별도 확인 필요 |
| 프로세스 사망(OOM/kill) | **로그에 아무것도 안 남는다** → 타임아웃이 유일한 방어 |

마지막 줄 때문에 **대기 루프에는 항상 상한**이 필요하다.

## Verification

- [ ] 종료 패턴이 **앞 단계 출력에 나타나지 않음**을 실제 로그로 확인했다
- [ ] 실패 종료도 같은 패턴에 걸린다
- [ ] 프로세스가 죽어도 빠져나온다(타임아웃)
- [ ] 알림을 받으면 **요약 줄을 실제로 읽는다** — "완료됨" 상태만 보고 넘기지 않는다

## Related

- [[piped-gate-masks-exit-code]] — 파이프가 성패를 가린다
- [[truncated-diagnostic-shows-only-the-passing-half]] — `tail` 로 잘라 보다 앞의 에러를 놓친다
- [[failure-feedback-blind-prefix-shows-only-passes]] — 통과 목록만 보여주는 피드백
