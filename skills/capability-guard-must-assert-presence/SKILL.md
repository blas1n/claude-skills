---
name: capability-guard-must-assert-presence
description: 에이전트/샌드박스의 능력을 제한하는 가드는 "금지된 것이 없음"만 검사하면 정작 자기가 존재하는 이유인 실패(능력이 0개)를 못 잡는다. 툴이 없는 에이전트는 실패하지 않고 '지어낸다'. 트리거: 툴/권한 allowlist·denylist 가드, "leaked tools" 검사, 샌드박스 격리 검증, 에이전트가 그럴듯한 거짓 결과를 success로 리턴.
---

# 가드는 "없음"이 아니라 "있음"을 검증해야 한다

## Problem

에이전트에게 우리 툴만 주고 로컬 툴은 뺏는 설계에서, 가드는 보통 이렇게 짠다:

```python
exposed = set(init_event["tools"])
leaked = exposed - set(allowed)      # 우리가 허가 안 한 게 노출됐나?
if leaked:
    abort()                          # ✅ 초과(excess)는 잡는다
```

- **증상**: CI 그린, 가드도 "통과". 그런데 프로덕션에서 에이전트가 **엉뚱한 답을 자신 있게** 내놓는다.
- **근본 원인**: `exposed = {}` (툴이 **하나도** 없음)일 때 `leaked`는 **공집합**이라 가드를 그냥 통과한다.
  가드가 **초과만 보고 부재(absence)를 안 본다.**
- **왜 치명적인가**: **툴이 없는 LLM 에이전트는 "툴이 없습니다"라고 말하지 않는다.**
  툴 호출을 **평문(prose)으로 흉내내고**, 그 결과를 **상상해서 답한다**:

  ```
  TEXT  I'll list the files now.
        <function_calls><invoke name="glob">...     ← 진짜 tool_use 아님. 그냥 텍스트.
  TEXT  The directory appears to be empty (no files found).   ← 완전한 허구
  RESULT success | turns: 1 | is_error: false                 ← 성공으로 보고됨
  ```

  **조용한 날조 > 시끄러운 크래시.** 크래시는 눈에 띄지만 이건 그대로 머지된다.

## Solution

가드가 **정확히 우리 집합**임을 요구하게 한다 — 초과와 **부재를 둘 다**:

```python
def _tools_are_exactly_ours(event, allowed) -> str | None:
    exposed = set(event.get("tools") or [])
    sanctioned = set(allowed)
    problems = []
    if leaked := sorted(exposed - sanctioned):
        problems.append(f"unsanctioned: {', '.join(leaked)}")
    if missing := sorted(sanctioned - exposed):      # ← 이 절이 핵심
        problems.append(f"our tools never arrived: {', '.join(missing)}")
    return "; ".join(problems) or None
```

부재 시 **작업을 중단**하라. 툴 없이 굴러간 턴의 산출물은 신뢰할 수 없다.

## Key Insights

- **"금지된 능력이 없다"와 "필요한 능력이 있다"는 다른 명제다.** 격리 가드는 전자만 검증하기 쉽고,
  실제 사고는 후자에서 난다. 두 방향 모두 단언하라 (`exposed == sanctioned`).
- **능력 0개는 no-op이 아니라 hallucination이다.** 빌드할 게 없는 코딩 에이전트가
  아무 코드나 고쳐서 ship 하는 것과 같은 계열 ([[lexical-gate-for-semantic-intent]]).
- 이 버그는 **유닛테스트로 안 잡힌다**: 가드 자체가 테스트돼 있어도, 테스트가
  "leaked=[] → pass"만 검증하면 부재 케이스를 그대로 통과시킨다.
  **가드를 짤 때 "이 가드가 존재하는 이유인 실패를 넣으면 정말 잡히나?"를 테스트로 써라.**
- 일반화: 샌드박스/권한/네트워크 격리 검증 전반에 적용된다.
  "인터넷이 차단됐다"만 보고 "DB에는 붙는다"를 안 보면 같은 함정.

## Red Flags

- 가드 코드에 `exposed - allowed`는 있는데 `allowed - exposed`가 없다.
- 에이전트가 `turns: 1`로 끝나며 그럴듯한 요약을 리턴한다 (툴을 쓸 일이었는데도).
- 툴 호출이 **텍스트 안에** 있다 (`<invoke name=...>`, `<function_calls>`).
- 산출물이 없는데 run이 `success`다 → 무엇으로 성공을 판정했는가?
- 리뷰 질문: **"이 가드에 '아무 능력도 없는' 입력을 주면 통과하는가?"** 통과하면 가드가 아니다.
