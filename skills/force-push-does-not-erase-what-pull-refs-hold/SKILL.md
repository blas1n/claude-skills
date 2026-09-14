---
name: force-push-does-not-erase-what-pull-refs-hold
description: private 레포를 public 으로 바꾸기 전 비밀을 지우려고 `filter-repo` + force push 를 해도 **GitHub 은 PR 마다 만든 `refs/pull/N/head` 로 옛 커밋을 붙잡고 있다** — 그 ref 는 사용자가 지울 수 없고(PR 삭제 불가), 공개되는 순간 `git fetch origin 'refs/pull/*/head:…'` 한 줄로 전부 회수된다. 실측: 세탁본 26커밋을 force push 했는데 원격 미러는 **70커밋**이었고 계좌번호·삭제한 문서가 그대로 꺼내졌다. **로컬이 깨끗한 것과 원격이 깨끗한 것은 다른 주장이다 — 신선한 `--mirror` 클론으로 재라.** 트리거 - private→public 전환, 이력에서 비밀 제거, filter-repo/BFG 사용 후 검증, "force push 했으니 지워졌다".
version: 1.0.0
task_types: [devops, review, workflow]
triggers:
  - pattern: "private 레포를 public 으로 전환하기 전 민감정보를 점검할 때"
  - pattern: "git filter-repo / BFG 로 이력에서 비밀을 지운 뒤 검증할 때"
  - pattern: "force push 로 옛 커밋이 사라졌다고 판단하려 할 때"
  - pattern: "레포 공개 여부를 '이슈 없을지 체크해줘' 로 물을 때"
category: trap
---

# force push 는 PR ref 가 붙잡은 것을 지우지 못한다

## Problem

2026-09-14, private 레포를 public 으로 돌리기 전 이력을 세탁했다. `git filter-repo` 로
민감 문서를 전 이력에서 제거하고 계좌번호를 치환한 뒤 force push 했다. 로컬 세탁본을
전수 스캔하니 **민감 패턴 0건**. 여기서 끝냈으면 그대로 공개했을 것이다.

공개 직전 **원격을 신선한 `--mirror` 로 다시 받아** 재보니:

```
로컬 세탁본 : 26 커밋
원격 미러   : 70 커밋          ← ?
```

```
refs/heads/main
refs/pull/1/head  …  refs/pull/14/head      ← 14개가 옛 커밋을 붙잡고 있다
```

그리고 `main` 에서 지운 파일이 **그대로 꺼내졌다**:

```console
$ git show refs/heads/main:docs/HANDOFF.md
fatal: path 'docs/HANDOFF.md' does not exist in 'refs/heads/main'

$ git show refs/pull/14/head:docs/HANDOFF.md | head -18
# BStockReport 진행 상황 (세션 인수인계)
- 두 계좌 distinct 확인 — bstalk3r `PA37Q72K7CTS`(equity $1,068,541 …
```

원격 전수 스캔: 계좌번호 각 **3건** · 홈 경로 **5건** · 내부 UUID · 배포 프로젝트명 —
force push 가 **하나도 못 지웠다.**

> GitHub 은 PR 이 열릴 때마다 `refs/pull/N/head` 를 만든다. **이 ref 는 지울 수 없다** —
> PR 자체를 삭제하는 기능이 없기 때문이다. force push 는 `refs/heads/*` 만 옮기고,
> pull ref 가 가리키는 객체는 계속 reachable 하다. 공개되는 순간 누구나 받아간다:
>
> ```bash
> git fetch origin '+refs/pull/*/head:refs/remotes/pull/*'
> ```

## Rule

### 1. 공개 전 검증은 반드시 **원격을 신선하게 mirror 클론**해서 한다

로컬 작업본은 pull ref 를 안 갖는다. 그래서 **로컬이 깨끗한 것은 원격이 깨끗하다는
근거가 못 된다.** 두 개는 다른 명제다.

```bash
git clone --mirror https://github.com/<owner>/<repo>.git /tmp/verify
cd /tmp/verify
git for-each-ref --format='%(refname)'        # pull ref 가 보이면 그게 답이다
git rev-list --all --count                    # 세탁본보다 많으면 옛 객체가 산다
```

전 객체를 실제로 열어서 스캔하라 — 파일 목록이 아니라 **blob 내용**을:

```bash
for o in $(git rev-list --all --objects | awk '{print $1}' | sort -u); do
  [ "$(git cat-file -t "$o" 2>/dev/null)" = blob ] && git cat-file -p "$o" 2>/dev/null
done > /tmp/all.txt
grep -cF '<지운 문자열>' /tmp/all.txt          # 0 이어야 한다
```

### 2. 0을 세기 전에 **양성 대조군**을 쳐라

지운 문자열이 0건인 것과, 스캔이 애초에 아무것도 못 읽는 것은 구분이 안 된다.
살아 있어야 할 문자열(프로젝트 이름 등)을 같이 세서 **스캔이 작동함**을 먼저 보여라.

### 3. 이미 공개 레포에서 비밀이 발견됐다면 — 세탁으로 못 되돌린다

PR ref 가 있는 한 force push 는 무력하다. 실효 있는 선택지는 둘뿐이다:

| 방법 | 결과 |
|---|---|
| **새 레포를 만들어 세탁본만 push** | pull ref 가 애초에 없다. **확실하다** |
| GitHub Support 에 unreachable 객체 GC 요청 | 며칠 걸리고 보장이 없다. pull ref 자체는 남는다 |

그리고 **노출된 자격증명은 어느 쪽이든 로테이션해야 한다** — 세탁은 "앞으로 안 보인다"일
뿐, 이미 누가 받아갔는지는 세탁이 답하지 못한다.

### 4. 새 레포로 갈 때의 순서

되돌릴 수 없는 것을 마지막에 둔다.

1. **백업** — `git clone --mirror` + 이슈/PR 을 `gh ... --json` 으로 덤프
   (미러는 코드만 담는다. 이슈·PR 본문은 별도다)
2. 옛 레포 **rename** (URL 을 새 레포가 물려받게)
3. 새 레포를 **private 으로** 만들어 push
4. **신선한 mirror 로 검증** ← 이 단계가 이 스킬의 전부다
5. 게이트 실행 (테스트·lint)
6. **그 다음에** public 전환
7. 로컬 클론 remote 갱신 · 옛 레포 삭제

### 5. 이슈·PR **본문**도 공개된다

코드만 보지 마라. 전환 시 이슈와 PR 이 전부 공개된다. 본문에 계좌번호·내부 경로·다른
레포의 인프라 구조를 적어뒀다면 그것도 세탁 대상이다 (`gh issue edit` / `gh pr edit`).

## Checklist

- [ ] 원격을 **`--mirror` 로 새로 받아** 검증했나 (로컬 작업본이 아니라)
- [ ] `git for-each-ref` 로 **pull ref 존재**를 확인했나
- [ ] 커밋 수가 세탁본과 **일치**하나 (많으면 옛 객체가 산다)
- [ ] blob **내용**을 스캔했나 (파일 목록이 아니라)
- [ ] 양성 대조군으로 스캔이 작동함을 보였나
- [ ] 이슈·PR **본문**도 스캔했나
- [ ] 노출됐던 자격증명을 **로테이션**했나
- [ ] 되돌릴 수 없는 단계(공개·삭제)를 **마지막**에 뒀나

## Related

- `a-living-doc-repeats-a-fact-and-updates-only-one-copy` — 옮기기 전에 생존율을 재라
- `absence-measurement-validity-check` — 0을 세기 전에 그 0을 만드는 파이프라인이 도는지 확인하라
- `a-check-that-cannot-flip-is-not-measuring-anything` — 로컬만 보는 검사는 원격 결함에 대해 빨개질 수 없다
