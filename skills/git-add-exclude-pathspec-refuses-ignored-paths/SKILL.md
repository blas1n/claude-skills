---
name: git-add-exclude-pathspec-refuses-ignored-paths
description: `git add -A -- . ':(exclude).venv'` 로 찌꺼기를 빼려 하면, 그 경로가 **존재하고 또 .gitignore 에 있을 때** git 이 스테이징 전체를 exit 1 로 거부한다("The following paths are ignored by one of your .gitignore files"). 두 조건이 다 필요해서 테스트 픽스처에 .gitignore 가 없으면 영원히 통과한다. 처방은 `git add -A` 후 `git reset -- <찌꺼기>`. 트리거: 자동 커밋 파이프라인, `:(exclude)` pathspec, "커밋이 조용히 안 됨", staged 인데 commit 안 된 트리.
---

# `:(exclude)` pathspec 이 무시되는 경로를 지목하면 `git add` 가 통째로 거부한다

## Problem

에이전트/CI 가 작업 트리를 자동 커밋할 때, 빌드 찌꺼기를 빼려고 이렇게 쓴다:

```bash
git add -A -- . ':(exclude).venv' ':(exclude)node_modules' ':(exclude).pytest_cache'
```

- **증상**: 파이프라인이 **아무것도 커밋하지 못한다.** 트리에는 `git add` 까지만 된 변경이
  남는다(`git status --porcelain` 이 `M ` — staged, 워킹트리는 clean).
- **에러**:
  ```
  The following paths are ignored by one of your .gitignore files:
  .pytest_cache
  .ruff_cache
  .venv
  hint: Use -f if you really want to add them.
  ```
  exit 1, 스테이징 0.
- **근본 원인**: `:(exclude)` 도 **pathspec** 이다. git 은 pathspec 이 무시되는 경로를
  **명시적으로 지목**하면 거부한다 — 빼려는 의도인지 넣으려는 의도인지 구분하지 않는다.
- **흔한 오해**: "`--ignore-errors` 를 붙이면 되겠지." → **안 된다**(실측 exit 1 그대로).

### 왜 테스트가 통과하고 있었나 — 조건이 **둘**이다

거부하려면 그 경로가 **①실제로 존재**하고 **②그 레포가 그것을 무시**해야 한다.

| 픽스처 | `.venv` 존재 | `.gitignore` 에 있음 | 결과 |
|---|---|---|---|
| 흔한 테스트 | ✅ (일부러 만듦) | ❌ **안 만듦** | **통과** (그냥 untracked) |
| 실제 레포 | ✅ | ✅ | **실패** |

테스트가 찌꺼기를 만드는 것까지는 하는데 `.gitignore` 를 안 만들면, 거부 조건이 성립하지
않아 영원히 green 이다. 실서비스는 예외 없이 `.venv` 를 gitignore 한다.

## Solution

**전부 스테이징한 뒤 찌꺼기를 도로 뺀다.**

```bash
git add -A                                    # pathspec 없음 → 지목할 게 없어 거부도 없다
git reset -q -- .venv node_modules __pycache__ .pytest_cache .ruff_cache
```

실측(git 2.52):

| 형태 | 찌꺼기 존재 + gitignore 됨 |
|---|---|
| `git add -A -- . ':(exclude)X'` | **exit 1**, 스테이징 0 |
| 위 + `--ignore-errors` | **exit 1** |
| `git add -A` → `git reset -- X` | **exit 0**, 정상 |

`git reset -- <paths>` 의 성질(전부 실측):
- 없는 경로가 섞여 있어도 **exit 0**(멱등)
- 스테이징 안 된 경로도 **exit 0**
- **파일 자체는 안 지운다** — 인덱스에서만 뺀다(다시 `??` untracked 가 됨)
- 첫 커밋 전 레포에서도 동작

⚠️ **제외 목록을 지우고 `.gitignore` 에만 맡기지 마라.** 그건 더 단순한 오답이다 — 레포가
`node_modules` 를 무시하지 **않으면** 그대로 커밋된다. unstage 단계가 잡는 것이 정확히 그
경우다. 테스트에 gitignore 안 된 찌꺼기를 하나 넣어 이 오답을 막아라.

## Key Insights

- **`:(exclude)` 는 "무시하라"가 아니라 "이 경로를 언급한다"이다.** git 에게는 지목이고,
  지목된 ignored 경로는 거부 사유다.
- **거부 조건이 AND 두 개면 픽스처는 둘 다 만들어야 한다.** 하나만 만든 픽스처는
  "조건을 재현했다"는 착각을 준다 — 이 결함이 유닛 6071개와 앞선 E2E 를 통과한 이유다.
- **테스트 레포는 진짜 레포처럼 생겨야 한다.** `.gitignore` 는 장식이 아니라 동작을
  바꾸는 파일이다. 픽스처에서 그걸 생략하는 순간 다른 git 을 테스트하게 된다.
- 다음에 먼저 볼 것: 자동 커밋이 조용히 실패하면 **`git status --porcelain` 의 첫 칸**을
  봐라. `M ` (staged, clean worktree) 면 add 는 됐고 commit 이 안 된 것, 스테이징 자체가
  실패했으면 아무것도 안 올라가 있다.

## Red Flags

- 커밋 파이프라인에 `:(exclude)` 또는 `git add -- <경로 목록>` 이 있다
- 자동 커밋이 "변경 없음"으로 조용히 끝나는데 트리에는 변경이 있다
- 실 git 테스트가 찌꺼기 디렉터리는 만들면서 `.gitignore` 는 안 만든다
- `--ignore-errors` / `-f` 를 붙여서 넘기려는 유혹 (`-f` 는 찌꺼기를 **커밋한다**)
