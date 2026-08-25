---
name: failure-duration-names-the-timeout-that-caused-it
description: "실패까지 걸린 시간을 코드베이스의 타임아웃 상수들과 대조하라. 합이 맞으면 로직 버그가 아니라 두 층이 서로를 기다리다 죽은 것이고, 범인은 응답하지 않은 쪽이다."
version: 1.0.0
task_types: [debugging, testing, evaluation]
triggers:
  - pattern: "CI 에서만 나고 로컬에서 재현 안 되는 실패"
  - pattern: "에러 메시지가 프로덕션 코드를 가리키는데 그 코드가 멀쩡해 보임"
  - pattern: "flaky test / intermittent timeout / exit code None / result is None"
  - pattern: "재현이 안 돼서 어디부터 봐야 할지 모를 때"
category: technique
---

# 실패 소요 시간이 원인을 지목한다

## 기법

버그를 열기 전에 **실패까지 걸린 시간을 먼저 재라.** 그리고 코드베이스의
타임아웃 상수들과 대조하라.

```
실패 소요 시간 ≈ 타임아웃A + 타임아웃B   →   로직 버그가 아니다.
                                            두 층이 서로를 기다린 것이고,
                                            범인은 "응답하지 않은 쪽"이다.

실패 소요 시간 < 1초                   →   타임아웃이 아니다.
                                            로직 / 설정 / 부재를 봐라.
```

이 산수는 **재현이 안 되는 결함에서 특히 강력하다.** 재현 없이도 조사 범위를
"로직 전체"에서 "누가 응답을 안 했나" 하나로 좁혀준다.

## 왜 이게 통하나

타임아웃은 **코드에 박힌 상수**다. 실패 시간이 그 상수(들)와 일치한다는 것은
어떤 코드도 "틀린 답"을 내지 않았다는 뜻이다 — 아무도 **답을 안 준 것**이다.
그러면 스택트레이스가 가리키는 곳은 대개 **무고하다**. 그건 기다리다 지친
쪽이지 실패한 쪽이 아니다.

## 실측 (BSVibe, 2026-08-25)

CI 가 이렇게 죽었다:

```
FAILED tests/supervisor/sandbox/test_client_worker_manager.py::test_list_dir_returns_entries
       SandboxError: list_dir '.': exit None
```

`client_worker_manager` 를 정확히 지목한다. 로컬은 통과. 부하를 줘도 재현 안 됨.

**시간을 쟀다:**

```
02:41:28  직전 테스트 PASSED
02:42:59  FAILED            ← 91초
02:43:00  다음 테스트 PASSED  ← 1초
```

상수를 찾았다:

```python
_FILE_OP_TIMEOUT_S = 30.0   # client_worker_manager
_AWAIT_SLACK_S     = 60.0   # 같은 파일
_FAKE_WORKER_BUDGET_S = 60.0  # 테스트 하네스
```

**30 + 60 = 90 ≈ 91.** 그 순간 방향이 바뀌었다 — 프로덕션 로직을 읽는 대신
"누가 60초 동안 응답을 안 했나"를 물었다. 답: **테스트의 가짜 워커**가 자기
60초 예산을 쓰고 **아무 말 없이 `return`** 했다. 무고한 프로덕션 모듈이
스택트레이스의 얼굴이 되어 있었다.

같은 세션에서 대칭 사례도 나왔다 — 다른 CI 실패는 **25초**에 났다. 테스트가
도는 시간이 아니다 → 타임아웃 아님 → 실제 원인은 `ruff format --check` 였다.

## 적용 절차

1. **시간을 재라.** CI 로그 타임스탬프, `--durations`, 전후 테스트와의 간격.
   "실패했다"만 보고 열지 마라.
2. **상수를 긁어라.** `grep -nE "_TIMEOUT|_BUDGET|_SLACK|timeout_s|deadline" ` —
   관련 모듈과 **테스트 하네스 양쪽 다**.
3. **합을 맞춰봐라.** 하나와 맞으면 그 층이 기다린 것, 둘의 합과 맞으면 두 층이
   차례로 기다린 것 — 그러면 **가장 안쪽에서 응답을 안 한 쪽**이 범인이다.
4. **즉시 실패면 반대로 가라.** 1초 미만이면 타임아웃 경로를 통째로 배제하고
   설정·부재·검증 게이트를 봐라.

## 함께 고칠 것

범인이 "조용히 포기한 쪽"으로 밝혀지면, 그 포기 경로가 **자기 이름을 대게**
만들어라. `return` 으로 끝나는 타임아웃 루프는 실패를 성공으로 위장하고,
상대의 타임아웃이 진짜 원인을 덮는다.

```python
# 전: 예산 소진 → 조용히 return  → 상대가 90초 더 기다렸다 엉뚱한 에러
# 후: 예산 소진 → 관측값과 함께 실패
raise AssertionError(
    f"fake worker saw no exec task on {stream} in {elapsed:.1f}s "
    f"({reads} xread calls, actions seen: {seen or 'none'}). "
    "The harness failed, not the code under test."
)
```

관측값(시도 횟수·본 것·경과)이 핵심이다 — **재현 안 되는 CI 전용 결함은 그
숫자로만 좁혀진다**: read 가 적으면 굶은 이벤트 루프, read 는 많은데 본 게
없으면 잘못된 채널, 엉뚱한 게 보이면 프로토콜 불일치.

## 하지 말 것

- **재현 못 한 가설로 프로덕션 코드를 고치지 마라.** 시간 산수는 방향을 주지
  근본 원인을 주지 않는다. BSVibe 2026-08-25 에서도 "왜 60초 동안 못 받았나"는
  끝내 미상으로 남겼고, 대신 하네스가 다음에 스스로 지목하게 만들었다.
- **타임아웃을 늘려서 덮지 마라.** 그건 다음 번에 더 오래 걸리는 실패를 산다.
  (그 파일에는 이미 "CI flake 2026-08-10" 으로 한 번 늘린 이력이 있었다.)

## 관련

- 하네스가 프로덕션 얼굴을 쓰는 문제: 메모리
  `harness-failure-must-not-wear-the-products-face`
- `absence-measurement-validity-check` — 0 을 셀 때 producer 가 켜져 있는지
- `piped-gate-masks-exit-code` — `$?` 를 잘못 재는 함정 (시간과 종료코드 둘 다
  측정 대상이다)
