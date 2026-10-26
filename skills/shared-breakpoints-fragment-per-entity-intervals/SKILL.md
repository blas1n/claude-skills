---
name: shared-breakpoints-fragment-per-entity-intervals
description: 여러 개체(플레이어·유닛·세션)의 상태 구간을 "모든 개체의 사건 시각을 합친 경계"로 잘라 한 번에 계산하면, 한 개체의 연속 구간이 남의 사건마다 쪼개진다 — 공백·커버리지·최대 간격·쌍 매칭이 조용히 틀린다. 개체별로 인접한 같은 상태 구간을 병합하고, "구간 끝(open edge)" 비중 같은 센서로 확인하라. 트리거 - 생존/세션/활성 구간 계산, 공용 타임라인 경계(marks)로 상태 샘플링, per-entity coverage·gap 지표, 구간 경계를 넘는 쌍 제외 규칙, 예상보다 큰 "구간 시작/끝" 비중.
version: 1.0.0
task_types: [data-analysis, research]
triggers:
  - pattern: "computing per-entity alive/active intervals from a shared list of event times"
  - pattern: "gap or coverage metrics per entity inside state segments"
---

# 공용 경계로 자른 구간은 개체별로 병합해야 한다

hots-replay-analysis 2026-10-26 (PR #37 spatial feasibility)에서 얻은 교훈.

## 함정

- 플레이어별 생존 구간을 만들려고 **모든 플레이어의** 사망·부활 시각을 정렬한 경계 목록을 만들고, 경계 사이 중점에서 각 플레이어의 생존 여부를 샘플링했다. 상태 판정 자체는 맞다.
- 그런데 결과 구간을 그대로 썼다: 플레이어 A가 계속 살아 있어도 B가 죽은 시각마다 A의 구간이 끊긴다.
- 영향: 관측 공백을 "구간 안"으로만 세서 공백이 짧아지고, 끊긴 자리마다 "구간 끝(open edge)" 공백이 생겼다(생존 시간의 44%!). 같은 구간 안에서만 쌍을 만드는 오차 측정도 쌍이 빠졌다. 최대 공백 p50이 30초 → 실제 36초.

## 센서

- "구간 끝" 비중이 비정상적으로 크면(이번 44% → 고친 뒤 3.75%) 구간이 쪼개졌다는 신호. 개체당 구간 수 = 사망 수 + 1 근처인지 보라.

## 고친 방법

- 개체별로 같은 상태가 맞닿은 구간(`prev.end == next.start`)을 병합한 뒤 지표를 계산한다.
- 쌍 매칭·공백 계산은 병합된 구간 기준으로.

## 적용 방법

- 공용 경계로 상태를 샘플링하는 코드를 쓰면, 바로 다음 줄에 개체별 병합을 둔다.
- 지표를 내기 전에 개체당 구간 수와 구간 끝 비중을 한 번 출력해 본다.
