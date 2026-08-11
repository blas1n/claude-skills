---
name: github-merge-502-already-merged
description: `gh pr merge` 가 502/504 를 내도 머지는 이미 됐을 수 있다 — GitHub 는 머지를 수행한 뒤 PR 레코드 갱신에서 죽는다. 그러면 스쿼시 커밋은 main 에 있는데 PR 은 `state=open, merged=false` 로 남고, 브랜치도 안 지워진다. 재시도하기 전에 `git log origin/main` 을 먼저 봐라. 트리거: gh pr merge 502/Bad Gateway, "머지 실패"인데 CI 는 green, mergeStateStatus 가 갑자기 BEHIND, PR 이 열려 있는데 커밋이 main 에 있음.
---

# `gh pr merge` 의 502 는 "머지 안 됐다"가 아니다

## Problem

```
$ gh pr merge 736 --squash --delete-branch
non-200 OK status code: 502 Bad Gateway ... <center>nginx</center>
```

반사적으로 재시도하거나 "머지 실패"로 보고하게 된다. **둘 다 틀릴 수 있다.**

- **증상**: 머지 명령이 502. 이어서 `gh pr view` 를 보면 `state: OPEN`, `mergedAt: null`,
  `mergeStateStatus: BEHIND` — 전부 "안 됐다"로 읽힌다. 리모트 브랜치도 그대로 있다.
- **실제**: `git fetch && git log origin/main` 을 보면 **스쿼시 커밋이 이미 올라가 있다.**
- **근본 원인**: 머지는 두 단계다 — ①ref 를 전진시킨다 ②PR 레코드를 merged 로 표시하고
  브랜치를 지운다. 502 는 ① 이후 ② 에서 났고, GitHub 은 그것을 **되감지 않는다.**
  스쿼시 머지는 커밋 SHA 가 브랜치 tip 과 달라서 GitHub 의 자동 감지도 안 걸린다.
- **왜 위험한가**: 재시도하면 이미 반영된 변경을 다시 머지하려 들고(빈 머지 또는 충돌),
  "머지 실패"로 보고하면 **이미 배포 파이프라인이 물어간 변경**을 없는 것으로 취급하게 된다.

## Solution

502/504 를 받으면 **재시도 금지, 먼저 사실을 확인**한다:

```bash
git fetch -q origin
git log --oneline -3 origin/main            # 내 PR 번호의 스쿼시 커밋이 있는가?

# 있다면 — 내용까지 동일성 확인 (부분 반영이 아님을 증명)
git diff --stat origin/main <my-branch>     # 비어 있어야 한다

# 동일하면 머지는 끝난 것이다. PR 레코드만 손으로 정리한다
gh pr close <N> --comment "머지 API 502; 스쿼시 커밋은 main 에 반영됨(<sha>). 레코드만 수동 정리."
git push origin --delete <my-branch>
```

⚠️ `gh pr close --delete-branch` 는 다른 워크트리가 그 브랜치를 쓰고 있으면
`fatal: 'main' is already used by worktree at ...` 로 로컬 삭제에서 죽는다.
리모트 삭제는 `git push origin --delete` 로 따로 한다.

배포 확인도 잊지 마라 — 머지가 됐으므로 **autodeploy 폴러는 이미 물어간다**:

```bash
curl -s https://<api>/api/health          # git_sha 가 새 커밋인지
```

## Key Insights

- **API 에러는 "요청이 실패했다"이지 "아무 일도 안 일어났다"가 아니다.** 쓰기 API 는
  부분적으로 성공할 수 있고, 502 는 게이트웨이 계층이라 백엔드가 어디까지 갔는지 말해주지 않는다.
- **원본(ref)이 메타데이터(PR 레코드)보다 진실이다.** GitHub UI/`gh pr view` 는
  PR 레코드를 보여주는데, 실제로 배포를 결정하는 것은 `origin/main` 의 ref 다.
- `mergeStateStatus: BEHIND` 같은 부수 신호가 오해를 강화한다 — 그건 이미 전진한 main
  기준으로 다시 계산된 값이다.
- 다음에 먼저 확인할 것: **`git log origin/main`.** PR 상태 API 를 다시 부르지 마라.

## Red Flags

- 머지 명령이 5xx/timeout 인데 CI 는 전부 green 이었다
- PR 은 열려 있는데 `git log origin/main` 에 그 PR 번호의 커밋이 있다
- 머지 직후 `mergeStateStatus` 가 `BEHIND` 로 바뀌었다
- 재시도하려는 충동 — 그 전에 ref 를 봐라
