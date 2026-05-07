---
name: orchestrate-worktree-preflight-trap
description: /orchestrate-worktree로 ralph-loop 시작 전 (1) worktree base가 stale local main이 아닌지, (2) 본 PR 표면을 점유한 최근 머지 PR이 origin에 없는지 검증하지 않으면 8000+ lines 작업 후 add/add collision으로 폐기 위험.
---

# Orchestrate-Worktree Pre-flight Trap

## Problem

`/orchestrate-worktree` skill로 ralph-loop를 11 task / 60+ minutes / 8500 lines 돌린 직후, push 시점에 main과 add/add collision이 광범위하게 발생해 PR 자체를 폐기하고 다시 시작하는 사태.

- **증상**:
  - `git rebase origin/main` → 다수 파일 add/add CONFLICT (단순 rebase로 해결 불가, 두 구현이 같은 파일을 다르게 작성).
  - `git diff origin/main..HEAD --name-only`가 본 PR과 무관한 파일까지 포함해 보임.
  - PR mergeStateStatus = `DIRTY`, mergeable = `CONFLICTING`.
- **근본 원인 두 개 (직렬로 발생)**:
  1. **worktree stale base**: `~/Works/_infra/scripts/create-worktree.sh`는 .bare repo HEAD를 base로 사용. .bare HEAD는 local main(`refs/heads/main`)과 같은 ref를 가리키므로, **local main이 stale이면 worktree도 stale 상태에서 출발**. 흔한 시나리오: local에서 다른 branch(예: `fix/login-...`)를 활성화해놓은 상태로 `git pull origin main` 실행 — pull은 활성 branch만 fast-forward하고 main은 안 건드림. `git fetch`로 origin/main은 갱신되지만 local main은 stale.
  2. **동시 표면 점유 PR 미스캔**: ralph-loop 시작 전 본 PR이 만들/수정할 파일 path들이 origin/main의 최근 머지 PR과 겹치는지 확인하지 않음. ralph는 그 사실 모르고 같은 표면을 자체 구현으로 채워버림 → push 시 add/add collision.
- **흔한 오해**:
  - "`git pull origin main`이 통과했으니 local main은 최신" — pull은 활성 branch에만 작용.
  - "Worktree create 메시지에 'HEAD is now at <commit>' 떴으니 OK" — 그 commit이 origin/main인지 검증 안 됨.
  - "rebase로 해결 가능" — 같은 파일을 양쪽이 _독립적으로_ 새로 만든 add/add는 두 다른 구현의 의미적 통합이 필요해 시간 비용이 ralph 재실행과 비슷하거나 큼.

## Solution

ralph-loop 시작 전 두 단계 pre-flight check:

### Step 1: local main을 origin/main에 강제 동기화

```bash
# 활성 branch와 무관하게 main을 ff-update.
git -C ~/Works/<PROJECT>/main fetch origin main
git -C ~/Works/<PROJECT>/main checkout main
git -C ~/Works/<PROJECT>/main pull --ff-only origin main
```

또는 worktree 생성 직후 강제 리셋:

```bash
~/Works/_infra/scripts/create-worktree.sh <PROJECT> <branch>
cd ~/Works/<PROJECT>/wt/<wt-name>
# Verify base == origin/main
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" || git reset --hard origin/main
```

### Step 2: 표면 충돌 사전 스캔

tasks.json 작성 후, ralph 시작 전:

```bash
# 1. 본 PR이 만들/수정할 path 목록 (tasks.json에서 추출 또는 추정)
PLANNED_PATHS=( "auth-app/lib/handlers/api-tokens" "auth-app/lib/handlers/oauth/token.ts" ... )

# 2. 본 worktree base 시점부터 origin/main까지 머지된 PR 조회
BASE_DATE=$(git log -1 --format=%cI HEAD)
gh pr list --state merged --base main \
  --search "merged:>$BASE_DATE" \
  --json number,title,mergedAt --limit 30

# 3. 각 머지 PR의 변경 파일과 PLANNED_PATHS 겹침 확인
gh pr view <pr-number> --json files --jq '.files[].path'
```

겹치는 머지 PR이 있으면:
- 해당 PR이 만든 인프라/유틸을 reuse하도록 tasks.json 수정 (재발명 금지).
- 같은 endpoint/file을 점유하는 경우 본 PR은 _확장_(grant_type 분기 추가 등)으로 재정의.
- PROMPT.md에 "EXISTING infra at <path> — REUSE not REPLACE" 지시 명시.

### Step 3: 매 ralph iteration 후 main drift 모니터

장시간 ralph-loop(1+ 시간) 중 main이 또 머지될 수 있다. iteration 사이에 fetch + diff stat 짧게 체크해 표면 침범 여부 감시.

## Key Insights

- **5분 사전 점검 vs 60분 폐기**: ralph-loop 11 task = 8500 lines를 폐기하는 비용이 1시간을 잃는 것이 아니라 LLM 토큰 비용 + 컨텍스트 단절까지 포함한다. 시작 전 5분 grep + gh CLI 호출로 충분히 회피.
- **`git pull origin main`은 활성 branch에만 작용**: 활성 branch가 main이 아니면 stale 안고 진행됨에도 명령 자체는 성공함. "Already up to date" 메시지는 활성 branch 기준이지 origin/main 기준이 아니다.
- **add/add CONFLICT은 의미적 충돌**: 단순 rebase로 풀리지 않는다. 두 PR이 같은 파일을 _독립적으로_ 만들었으면 한쪽 폐기 + 다른 쪽 위에 재작성이 빠르다.
- **create-worktree.sh의 base는 .bare HEAD**: .bare HEAD = local main의 ref. local main 갱신 안 되면 worktree도 stale. `git rev-parse HEAD == origin/main`을 worktree 생성 직후 강제 검증.

## Red Flags

이 함정을 의심해야 하는 신호:

- `git pull origin main`이 "Already up to date"인데 `git rev-list --count main..origin/main`이 0보다 큼 — 활성 branch가 main이 아님.
- worktree 생성 메시지의 "HEAD is now at <commit>" 의 commit이 `gh repo view --json defaultBranchRef`로 본 origin HEAD와 다름.
- ralph 끝난 후 push 시 GitHub mergeStateStatus가 `DIRTY` (보통 `BLOCKED`/`CLEAN`/`UNSTABLE` 정상 흐름).
- `git diff origin/main..HEAD --name-only` 출력에 ralph가 절대 만들지 않은 파일 (예: `oauth-client.ts`)이 섞여 있음 → 두 PR의 합집합 표시 = 두 base가 어긋남.
- 최근 머지된 PR의 title에 "auth", "oauth", "token", "session" 등 본 PR keyword와 겹치는데 그 PR을 안 본 상태.
- 같은 endpoint(예: `/api/oauth/token`)를 본 PR이 "신규 작성"하려는데 main에 이미 그 endpoint route 파일이 존재.
