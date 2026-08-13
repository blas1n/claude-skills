---
name: seam-must-assert-what-the-consumer-sees
description: 시임(seam)의 생산자 쪽만 보고 "정리하는 게 맞다"고 추론해 상태를 지우면, 그 상태가 소비자에게는 인계 그 자체일 수 있다. 테스트를 그 추론대로 쓰면 green 이 추론을 검증해준 것처럼 보인다. 트리거 - 핸드오프/재투입/재시도 경계 설계, cleanup·abort·reset·clear 를 추가할 때, "리소스를 돌려줘야 하니까 정리한다", 다음 단계가 "할 일이 없다"고 보고하며 아무것도 안 함.
---

# 시임을 만들 때 소비자가 무엇을 보는지를 단언하라

## Problem

BSVibe #743: 머지워치가 PR 최신화 중 conflict 를 만나면 `git merge --abort` 를 했다.

추론은 이랬다 — 워크트리는 파운더 머신의 회수 가능한 자원이고(#736 리퍼), 머지 중인
트리는 리퍼가 영원히 거부한다. 그러니 정리하고 넘기는 게 맞다. 테스트도 그렇게 썼다:

```python
async def test_a_conflicted_merge_is_aborted_before_the_worktree_goes_back():
    assert any(c.startswith("git merge --abort") for c in box.commands)
```

**green 이었다. 그리고 틀렸다.**

그 충돌 상태가 **인계 그 자체**였다. 재투입된 에이전트는 그 머지 *안에서* 해결해야
base 를 조상으로 갖는 커밋을 만든다. abort 된 깨끗한 트리를 받은 에이전트는:

> "충돌 마커가 없습니다. 이미 해결되었습니다."

라고 보고하고 파일을 손으로 고쳐 **선형 커밋**을 만들었다. 내용은 화해됐지만
`merge-base --is-ancestor` 는 NO — PR 은 영원히 dirty, 폴마다 같은 충돌 재투입,
재시도 소진, 에스컬레이션.

리퍼 걱정 자체도 거꾸로였다. **머지 중인 트리는 미해결 작업이 있는 트리이고,
리퍼가 거부하는 건 안전장치가 제대로 도는 것이다.** 에이전트가 해결·커밋하면
깨끗해져 회수된다.

## Why the test didn't help

테스트가 **요구사항이 아니라 내 추론을 단언했다.** 나는 시임의 *생산자* 쪽(리소스를
돌려주는 쪽)만 보고 결론을 냈고, 그 결론을 그대로 assert 로 옮겼다. green 은
"이 코드가 내가 생각한 대로 동작한다"만 말해주지 "내가 생각한 게 맞다"를 말해주지 않는다.

→ 형제 함정: [[boundary-test-must-not-supply-the-answer]]

## Solution

핸드오프 경계에서 상태를 지우기 전에 **소비자 쪽에서** 물어라:

1. **다음 단계는 무엇을 보고 일을 시작하는가?** 그 상태가 입력이면 지우면 안 된다.
2. **다른 실행 경로는 어떻게 하고 있나?** BSVibe 서버 모델은 애초에 abort 하지 않았고
   (최신화가 에이전트의 클론에서 일어나므로 충돌이 자연히 남는다), 그게 정답이었다.
   **두 경로가 갈리면 대개 새로 만든 쪽이 틀렸다.**
3. **"정리해야 한다"는 압박이 어디서 오나?** 그 자원 관리자가 이미 거부로 자신을
   지키고 있다면(`git worktree remove` 가 force 없이 거부하듯), 정리는 내 일이 아니다.

테스트는 소비자 요구로 쓴다:

```python
async def test_a_conflicted_merge_is_LEFT_for_the_agent_to_resolve():
    """resolving INSIDE the merge is what produces a commit with base as a
    parent, which is the only thing that makes the PR mergeable."""
    assert not any("merge --abort" in c for c in box.commands)
```

정리가 정말 필요한 좁은 경우는 따로 남긴다 — unmerged 경로가 **없는** 머지 실패
(잘못된 ref·더러운 트리)는 넘길 충돌이 없으므로 그때는 abort 가 맞다.

## Detection

- 다음 단계가 "할 일이 없다 / 이미 되어 있다"고 보고하며 아무것도 안 한다
- 재시도가 같은 지점을 반복하다 에스컬레이션된다
- 같은 계약의 두 구현이 cleanup 여부에서 갈린다
