---
name: piped-gate-masks-exit-code
description: 로컬에서 CI 게이트를 돌릴 때 `ruff check ... | tail -1` 처럼 파이프를 걸면 파이프라인 종료코드는 마지막 명령(tail)의 것이라 실패가 통째로 숨는다. `&&` 체인은 그대로 통과하고 "전부 green"이라고 보고하게 된다. 트리거: 로컬은 green인데 CI에서 lint/test 실패, `cmd | tail`, `cmd | head`, `set -e` + 파이프.
---

# 파이프는 종료코드를 삼킨다 — 로컬 게이트가 거짓말을 한다

## Problem

CI와 똑같이 돌린다며 이렇게 쓴다:

```bash
uv run ruff check backend/ | tail -1 && \
uv run mypy backend/ | tail -1 && \
uv run pytest -q | tail -4          # ← "5000 passed" 만 보고 green 이라 판단
```

- **증상**: 로컬은 "All checks passed / 5000 passed"인데 **CI에서 lint 또는 test 실패**.
- **근본 원인**: **파이프라인의 종료코드는 마지막 명령의 것**이다. `ruff`가 8개 에러로 exit 1을 내도
  `tail`이 exit 0을 내므로 **`&&` 체인이 그대로 진행**되고, 사람은 tail이 보여준 마지막 줄만 본다.
- **더 나쁜 케이스**: `pytest ... | tail -4` → 실패 목록(FAILED 22줄)이 **화면에도 로그파일에도 안 남는다.**
  요약 줄만 남아서 "22 failed"를 보고도 상세를 못 본다. 재현하려 또 12분을 태운다.

## Solution

**게이트는 종료코드로 판정한다. 출력은 파일로 남긴다.**

```bash
set -e                      # 각 단계 실패 시 즉시 중단
uv run ruff check backend/ tests/ > /dev/null      # 파이프 없음 → exit code 살아있음
uv run ruff format --check backend/ tests/ > /dev/null
uv run mypy backend/ > /dev/null
uv run lint-imports > /dev/null
uv run pytest -q > gate.log 2>&1                   # 전체 출력 보존
grep -cE '^(FAILED|ERROR)' gate.log                # 실패 목록을 실제로 읽는다
```

꼭 파이프를 써야 하면:

```bash
set -o pipefail             # 파이프라인이 첫 실패의 exit code를 승계
cmd | tail -1
# 또는
cmd; rc=$?; ...             # 종료코드를 명시적으로 캡처
echo "EXIT=$?"              # 최소한 찍어서 눈으로 확인
```

## Key Insights

- **`tail`/`head`/`grep`을 게이트에 물리면 그 순간 게이트가 아니라 "요약 뷰어"가 된다.**
  green 판정의 근거가 사람의 눈이 되고, 눈은 마지막 4줄만 본다.
- 이건 "체크가 자기가 검사해야 할 것을 못 보는" 버그 클래스다 —
  [[capability-guard-must-assert-presence]]와 같은 뿌리. **부재를 검증하지 않는 검사는 검사가 아니다.**
- **로그를 잘라내지 마라.** 12분짜리 스위트의 실패 목록을 tail로 날리면 재현 비용이 곱절이 된다.
  요약은 로그를 남긴 뒤 grep으로 만들어라.
- zsh/bash 기본은 pipefail이 **꺼져** 있다. CI 스크립트에 `set -eo pipefail`이 관용구인 이유.

## Red Flags

- 로컬 게이트는 green인데 CI만 빨갛다 (특히 lint/format처럼 결정론적인 단계).
- 게이트 스크립트에 `| tail`, `| head`, `| grep` 이 있다.
- 실패했는데 로그에 FAILED 목록이 안 보인다 → 잘라냈다.
- "전부 통과했습니다"라고 보고하기 직전: **각 단계의 exit code를 실제로 확인했는가?**
