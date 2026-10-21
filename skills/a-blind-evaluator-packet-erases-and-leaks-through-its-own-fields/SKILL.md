---
name: a-blind-evaluator-packet-erases-and-leaks-through-its-own-fields
description: 결과를 숨긴 "블라인드" LLM 평가 패킷(사후 판단 편향 통제)은 두 방향으로 동시에 실패한다. 행동 요약의 필터가 증거를 지워서 평가자가 행동을 반대로 읽거나, 메타데이터 필드(샘플 유형·이벤트 이름·소스 kind)가 숨긴 결과를 흘린다. 블라인드 패킷을 설계할 때, 블라인드 평가가 기대와 다르게 나왔을 때, 평가 대상 패킷을 고친 직후, "증거 없음"을 "불가"로 판정하는 레지스트리를 쓸 때 읽어라.
version: 1.0.0
task_types: [design, evaluation, llm]
triggers:
  - pattern: "LLM judge / evaluator that must not see outcome (hindsight, leakage control)"
  - pattern: "packet / prompt context built from summarized evidence (thresholded near/far)"
  - pattern: "re-evaluating after changing the context builder"
  - pattern: "registry covers only some entities; absence of evidence becomes 'not available'"
category: trap
---

# 블라인드 평가 패킷은 자기 필드로 증거를 지우고 결과를 흘린다

## Problem

리플레이 운영 코칭(hots-replay-analysis PR #23)에서 판단 시점마다 결과(오브젝트 승패, 이후 사망)를 뺀 패킷을 만들었다. 새 서브에이전트에게 그 패킷만 읽혀 평가했다. 검증기는 결과 fact_id를 인용하면 거부했다. 설계는 맞았지만 패킷이 두 방향으로 새고 있었다.

- **증거 삭제:** 실제 행동은 "목표 15 이내의 최초 증거"와 "30 초과 증거"만 요약했다. 대상의 유일한 관측점은 27.2 거리였고, 두 구간 어디에도 들지 않아 패킷에서 사라졌다. 평가자는 남은 "우클릭 0/12 근처"만 보고 "교전 회피"로 읽었다. 실제로는 아군 4명·적 4명이 지점에 몰린 싸움 한가운데 있었다.
- **결과 누출:** 위치 사실의 `quality` 필드에 `SUnitDiedEvent`가 그대로 있었다. 결과 칸을 아무리 빼도 "이 점은 사망 지점"이라는 정보가 사실 표로 들어갔다. 트리거 사실(오브젝트)에도 `winner_team`·`end_seconds`가 원본 그대로 실려 있었다.
- **증거 없음 = 불가:** 캠프 가용성은 등록된 수비 유닛의 생성으로 판정했다. 등록되지 않은 캠프는 목록에서 빠졌고, 그 결과 "가용 캠프 없음 → 맞교환 불가(derived)"로 단정됐다. 단일 샘플 경기에서는 안 보였고, 269경기 전체 점검에서 128경기가 걸렸다.
- 흔한 오해: "결과 칸을 빼고 검증기가 결과 인용을 막으면 블라인드다." 실제 누출과 삭제는 **남겨 둔 칸의 요약 규칙과 메타데이터**에서 일어난다.

## Solution

1. **행동 칸은 구간 요약보다 원자료를 우선한다.** 근처/먼 곳처럼 임계로 요약했다면, 같은 창의 모든 관측점을 거리와 함께 별도 칸으로 함께 넣는다. 요약은 해석이고, 원자료가 없으면 평가자는 공백을 "안 했다"로 읽는다.
2. **사실 표는 화이트리스트로 투영하고, 결과를 암시하는 메타데이터는 가린다.**
   - 이벤트 유형 기반 품질 값은 `periodic / event_point`로 일반화한다.
   - 트리거 사실에서 종료·승자·증거 목록을 뺀다.
   - "결과 이후에만 생기는 점"(부활 위치)은 행동 증거에서 제외한다.
   - 테스트로 고정한다: `assert "SUnitDied" not in repr(packet)`, `"winner" not in text`.
3. **플레이어 화면에 보이던 정보는 허용하되 표시한다.** 부활 타이머와 오브젝트 생성 시각은 나중 이벤트에서 읽지만, 판단 시점에 화면에 보이던 값이다. `derived` 등급에 출처 이벤트를 적어 허용한다. 키 이름은 단위가 드러나게 짓는다(`respawn_at_game_seconds`). `respawn_seconds`는 평가자가 대기 시간으로도 읽었다.
4. **패킷이 바뀌면 그 패킷으로 한 평가는 무효다.** 재생성한 패킷을 커밋본과 `cmp`로 비교한다. 바뀐 판단만 **새** 평가자로 다시 평가한다. 이전 평가자를 재사용하면 옛 맥락이 섞인다. 커밋 전에 "평가 = 이 바이트의 패킷"을 다시 확인한다.
5. **부분 레지스트리에서 증거가 없는 엔티티는 `None/unknown`이다.** 초기화(init) 목록을 기준으로 엔티티를 전부 나열하고, 증거가 없는 것은 `available: None`으로 둔다. 하나라도 `None`이면 "불가"를 단정하지 않는다.
6. **블라인드 결과를 결과와 대조하되 정당화로 쓰지 않는다.** "사전에 짚은 위험이 결과와 일관됨"까지만 말한다. 이 대조에서 패킷 결함이 드러난다. 평가자가 고칠 수 없던 칸이 `unknown`이면 피드백 자체가 나올 수 없었다.

```python
# compact(): 패킷 사실 표 투영
out = {k: fact[k] for k in FACT_FIELDS[fact["kind"]] if k in fact}   # whitelist (objective: no winner/end)
if fact["kind"] == "hero_position":
    out["quality"] = "periodic" if fact["quality"] == "periodic_integer_sample" else "event_point"
```

## Key Insights

- 블라인드 평가의 실패는 평가자 쪽이 아니라 **패킷 빌더**에서 난다. 평가자가 이상한 결론을 내면, 먼저 그 결론을 만든 칸을 원자료와 대조한다.
- 결과를 빼는 일(누출 방지)과 행동을 남기는 일(삭제 방지)은 서로 당긴다. 사망 지점처럼 "행동이자 결과"인 점은 **점은 남기고 유형만 가리는 것**이 균형점이다.
- 단일 샘플에서 통과한 판정 규칙도 부분 레지스트리 위에서는 다른 맵이나 경기에서 단정 오류를 낸다. 전체 코퍼스를 병렬로 점검하는 데 7분이면 충분하니 커밋 전에 돌린다.
- 관련: [[absence-measurement-validity-check]], [[a-failed-read-degraded-to-empty-becomes-a-measurement]]

## Red Flags

- 블라인드 평가자가 "X를 안 했다/피했다"고 판정했는데, 그 근거 칸이 임계 구간 요약뿐이다.
- 패킷 사실 표에 이벤트 원래 이름(`...Died...`, `...Revived...`)이나 승자·종료 필드가 남아 있다.
- 컨텍스트 빌더를 고친 뒤 기존 평가 파일을 그대로 두고 보고서를 다시 렌더링하려 한다.
- 레지스트리 기반 판정이 `False`를 내는데, 그 엔티티에 대해 관측된 증거가 하나도 없다.
