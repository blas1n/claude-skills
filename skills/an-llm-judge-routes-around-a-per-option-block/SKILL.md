---
name: an-llm-judge-routes-around-a-per-option-block
description: LLM 평가자(코치·판정자)가 근거 없는 부정 판정을 낼 때, 그 판정이 기대고 있던 선택지 하나만 막으면 평가자는 다음 선택지로 옮겨 같은 결론을 낸다. 고쳐야 하는 것은 선택지가 아니라 "부정 판정을 내려도 되는 조건"이다. LLM 판정·코칭에서 특정 오답을 막는 수정을 할 때, 수정 후에도 같은 사례에서 같은 결론이 다른 근거로 나올 때 읽어라.
version: 1.0.0
task_types: [evaluation, llm, design]
triggers:
  - pattern: "LLM judge/coach gives an unsupported negative verdict; fix by disabling the option it cited"
  - pattern: "after the fix the same case still gets the same verdict with a different justification"
  - pattern: "validator rules for LLM evaluations (abstention, confidence caps)"
category: trap
---

# LLM 평가자는 선택지 단위 차단을 돌아간다

## Problem

hots-replay-analysis PR #26. 아나가 오브젝트 지점에서 27.5 떨어진 라인으로 목적지를 옮겼다. 그 지점은 "라인 이동"으로도 "지점 옆 대기"로도 읽혔다(선택 분류에 다른 해석 존재). v0 코치는 "대기가 더 낫다"며 재검토 판정과 코칭을 냈다. 블라인드 검토자 둘 다 근거 없는 부정 평가로 채점했다.

- 첫 수정(v1): "대기"는 실제 선택의 다른 해석이므로 그 대안을 `unknown`으로 바꿨다(검증기가 unknown 대안을 더 낫다고 하면 거부). 맞는 수정이었다.
- 결과: v1 코치는 같은 사례에서 **"진입이 더 낫다"**로 대안만 바꿔 같은 코칭을 냈다. 확신도도 low→medium으로 올렸다. 다른 사례(4037e5aa)에서는 확신도 low인데 재검토 판정이 새로 나왔다. 검토자 둘 다 다시 근거 없는 부정 평가로 채점했다.
- 흔한 오해: "오답이 기댄 근거를 막으면 오답이 사라진다." LLM 평가자는 결론(여기서는 "이 선택은 나빴다")을 먼저 잡고, 남은 선택지에서 근거를 다시 고른다.

## Solution

1. **오답의 공통 전제를 찾는다.** 두 버전의 부정 판정이 같이 기댄 것은 특정 대안이 아니라 "실제 선택이 무엇이었는지 판단 시점 정보로 확정되지 않는다"는 사실과 "평가자 자신의 확신도 low"였다.
2. **그 전제에서 부정 판정 자체를 막는다(검증기 규칙).**
   - 선택 분류에 판단 시점 기준 다른 해석이 있으면 `questionable` 판정과 판단 코칭을 거부한다.
   - 평가자 판단 확신도가 low면 `questionable`과 코칭을 거부한다.
   - 선택지 단위 수정(`unknown` 표시)은 그대로 둔다. 둘 다 필요하다.
3. **같은 고정 평가셋으로 다시 돌리고, 수정의 근거가 된 사례를 따로 본다.** 숫자(부정 평가 수)뿐 아니라 그 사례의 판정 근거 문장이 바뀌었는지 읽는다. v2: 부정 평가 0, 해당 사례는 "라인 이동인지 대기인지 확정 불가"를 불확실성에 적고 acceptable.
4. **한계를 같이 적는다.** 수정 규칙이 같은 평가셋 사례에서 나왔으므로, 같은 셋으로 잰 개선은 낙관적이다. 새 표본에서 다시 잰다.

## Key Insights

- 선택지 차단은 "이 근거는 틀렸다"를 가르칠 뿐, "이 상황에서는 판정하지 마라"를 가르치지 않는다. 보류는 판정 단위 규칙으로만 강제된다.
- 수정 후 같은 사례가 **다른 이유로 같은 결론**을 내면, 그 결론의 진짜 원인은 아직 그대로다. 재평가 때 판정값뿐 아니라 근거가 된 대안 id를 버전별로 나란히 놓는다.
- 관련: [[a-blind-evaluator-packet-erases-and-leaks-through-its-own-fields]], [[lexical-gate-for-semantic-intent]] (자유 서술 금지 표현은 어휘로 거르지 않고 판정 구조로 막는다)

## Red Flags

- 근거 없는 판정 하나를 고치려고 그 판정이 인용한 대안/사실 하나만 비활성화한다.
- 재평가 결과 "같은 사례, 같은 판정, 다른 better_alternative".
- 평가자가 스스로 확신도 low나 "다른 해석도 가능"을 적었는데 부정 판정·코칭이 검증을 통과한다.
