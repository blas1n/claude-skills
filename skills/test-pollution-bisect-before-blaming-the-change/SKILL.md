---
name: test-pollution-bisect-before-blaming-the-change
description: 넓은 범위로 돌릴 때만 실패하고 단독으로는 통과하는 테스트는, 반대가 증명될 때까지 "테스트 간 오염"이다 — 내 변경 탓도, flaky 도 아니다. 파일 쌍으로 이분해 오염원을 찾고, 깨끗한 origin/main 워크트리에서 같은 순서로 재현해 기존 결함인지 가른다. 흔한 원인 두 가지 - 헬퍼의 raw `mod.X = fake`(복원 없음), "이번에 추가된 수"를 세는 멱등성 테스트. 트리거 - 단독 통과·묶음 실패, CI 는 초록인데 로컬 넓은 실행만 빨강, AttributeError 가 가짜 객체 이름(_Repo, _Fake)을 말할 때, "flaky" 라고 쓰려 할 때.
---

# 넓은 실행에서만 실패하면 오염부터 의심한다

## Problem

넓은 범위(`tests/workflow tests/delivery tests/glue`)로 돌리면 한 테스트가 실패하고 단독으로는 통과한다.
내 PR 의 회귀인지, 원래 있던 문제인지, 순서 의존인지 모른 채 "관련 없음"이라고 쓰기 쉽다 — 증거 없이.

## Solution

1. **에러 메시지가 가짜 이름을 말하는가** — `'_Repo' object has no attribute 'claim_due'` 처럼 테스트 더블의
   이름이 프로덕션 경로에서 나오면, 다른 테스트가 모듈 속성을 바꿔 놓고 안 돌려놓은 것이다.
   `grep -rn "^\s*mod\.[A-Za-z_]* = " tests | grep -v monkeypatch` 로 raw 대입을 찾는다.
2. **파일 쌍으로 이분** — `pytest A target -p no:randomly`. 디렉터리 → 파일로 좁힌다. 두 파일로 재현되면 끝.
3. **기존 결함인지 가른다** — 깨끗한 main 워크트리에서 같은 순서로:
   ```bash
   git worktree add --detach $SCRATCH/mainwt origin/main
   cd $SCRATCH/mainwt && /path/to/wt/.venv/bin/python -m pytest <같은 인자>
   # python -m pytest 는 cwd 를 sys.path 앞에 둔다 → backend 가 main 워크트리 것으로 잡힌다.
   # 먼저 python -c "import backend; print(backend.__file__)" 로 확인. uv run 은 거기 venv 가 없어 실패한다.
   git worktree remove --force $SCRATCH/mainwt
   ```
4. **고친다**
   - raw `mod.X = fake` → `monkeypatch.setattr`. 헬퍼가 monkeypatch 를 못 받으면 autouse fixture 가 원래 값을
     `monkeypatch.setattr(mod, "X", mod.X)` 로 먼저 등록 → 매 테스트 뒤 복원
   - "추가된 수"(`len(after) - len(before) == 1`) → 깨끗한 상태에서 시작해 **최종 개수**를 센다. 델타 0 은
     멱등성 그 자체라서, 앞선 테스트가 이미 설치했으면 정상 동작이 실패로 읽힌다
5. **절단으로 확인** — 고친 테스트가 실제 결함(가드 제거, 설치 제거)에서 여전히 빨강인지
6. 마지막에 전체 스위트를 **한 프로세스에서** 한 번 — 이 순서에서 다른 오염이 없다는 증거

## Key Insights

- "단독 통과" 는 무죄 증명이 아니라 오염의 신호다
- CI 초록은 CI 의 순서에서만 초록이다
- 기존 결함이라는 주장은 main 에서 재현해야 쓸 수 있다 (bsvibe 2026-10-06: 두 건 모두 main `def42eb` 에서 재현)
