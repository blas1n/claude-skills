---
name: cwd-resets-across-a-background-task-boundary
description: 워크트리에서 작업하다 백그라운드 작업을 띄우고 그 완료 알림으로 돌아오면, `cd` 를 한 번도 안 쳤는데 셸의 cwd 가 기본 작업 디렉터리로 돌아가 있다. 상대경로 편집이 조용히 **엉뚱한 git 트리**에 떨어진다. "절대경로로 cd 해라"는 규율은 이걸 못 막는다 — 내가 cd 를 안 했기 때문이다. 트리거 - 워크트리 + 백그라운드 테스트/빌드, 알림 복귀 직후 첫 명령, "방금 되던 `.venv/bin/...` 가 no such file", 두 트리에 편집이 흩어짐.
---

# 백그라운드 작업 경계를 넘으면 cwd 가 스스로 리셋된다

## Problem

워크트리에서 정상적으로 작업 중이었다:

```bash
cd /Users/me/proj/wt/my-branch && ls        # 여기서 한 번 cd
uv venv --python 3.11 && uv sync            # 상대경로 — 동작함
uv run pytest tests/my_guard.py             # 동작함
git --no-pager diff --stat                  # 워크트리 변경분이 정확히 나옴 ✅
```

그리고 오래 걸리는 게이트를 **백그라운드로** 띄운다. 완료 알림이 오고, 이어서:

```bash
uv run ruff format --check backend/
# error: Failed to spawn: `ruff` — No such file or directory
.venv/bin/ruff format --check backend/
# no such file or directory: .venv/bin/ruff
pwd
# /Users/me            ← 기본 작업 디렉터리. cd 를 친 적이 없다
```

- **증상**: 방금까지 되던 상대경로가 갑자기 전부 깨진다. `.venv` 가 "없다"고 한다.
- **근본 원인**: 백그라운드 작업 완료로 재진입할 때 셸이 **기본 작업 디렉터리에서 새로 시작**한다.
  `cd` 는 셸 상태고, 그 상태가 경계를 넘어 살아남지 않는다.
- **진짜 위험은 에러가 아니다.** 에러는 친절한 쪽이다. 위험한 건 **성공하는 상대경로**다 —
  두 트리가 같은 레이아웃이므로 `plugin/foo/plugin.py` 편집은 **main 트리에서도 성공한다.**
  그러면 워크트리는 비어 있고 main 은 더러워지며, 그 저장소에서 dirty main 은
  autodeploy 를 영구히 막는다.

## Solution

**경계를 넘은 뒤 첫 명령은 cwd 를 검증하거나, 애초에 cwd 에 의존하지 마라.**

```bash
# ① 도구는 -C / 절대경로로 — cwd 에 의존하지 않는다
git -C /Users/me/proj/wt/my-branch status --short
/Users/me/proj/wt/my-branch/.venv/bin/python -m pytest ...

# ② 꼭 cd 해야 하면 매 호출마다 붙인다 (한 번 쳐두고 유지된다고 믿지 마라)
cd /Users/me/proj/wt/my-branch && .venv/bin/ruff check backend/

# ③ 편집을 커밋하기 전에 두 트리를 대조한다 — 이게 마지막 방어선
git -C .../wt/my-branch status --short
git -C .../main         status --short     # 여기가 비어 있어야 정상
```

## Key Insights

- **"`cd` 는 절대경로로" 규율은 이 실패를 못 막는다.** 그 규율은 *내가 친 `cd`* 를 겨눈다.
  여기서는 아무도 cd 를 안 쳤고 cwd 가 알아서 움직였다. **원인이 다르면 가드도 달라야 한다.**
- **터미널 에러는 운이 좋은 경우다.** `.venv/bin/ruff` 가 없다고 소리쳐 준 덕에 알아챘다.
  같은 상황에서 `sed -i` 나 heredoc write 는 **조용히 성공**한다. 실패가 시끄러운 명령이
  먼저 걸리길 기대하지 마라.
- 백그라운드 작업은 **셸 상태의 경계**로 취급하라 — cwd 뿐 아니라 export 한 env 도 같다.
  게이트를 재실행할 때 `BSVIBE_DATABASE_URL` 같은 걸 다시 export 해야 하는 이유.
- 같은 결과(엉뚱한 트리 편집)에 이르는 길이 최소 둘이다 — 내가 친 `cd`,
  그리고 이 리셋. **결과를 기준으로 방어하라**: 커밋 전 두 트리 `git status` 대조.

## Red Flags

- 알림으로 복귀한 직후 첫 명령이 "no such file" / "Failed to spawn" 을 낸다.
- 워크트리 `git status` 가 비었는데 편집한 기억이 있다. (반대로 main 이 더럽다)
- 방금까지 되던 `uv run` 이 갑자기 다른 프로젝트의 의존성을 본다.

## Related

- [[piped-gate-masks-exit-code]] — 같은 백그라운드 게이트에서 나온 짝 함정.
  완료 알림의 "exit code 0" 은 체인 **마지막** 명령의 것이다.
- [[orchestrate-worktree]] · [[agent-executor-host-cwd-leak]] — cwd 가 새는 다른 층.
