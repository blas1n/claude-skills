---
name: a-text-similarity-is-dominated-by-the-documents-own-name
description: 문서 간 TF/bag-of-words 유사도(공시 텍스트 diff, 버전 비교, 중복 탐지)에서 **문서가 자기 이름을 가장 많이 말한다** — 회사명·제품명·작성자명이 최빈 토큰이라 그 표기가 바뀌면(리브랜드, 붙여쓰기, 합병명) 내용이 그대로여도 유사도가 무너지고, 반대로 이름 반복이 유사도를 1 쪽으로 끌어올린다. 이상값을 보면 추출부터 의심하지 말고 **두 문서의 최빈 토큰을 나란히 찍어라.** 이름을 빼는 "교정"은 신호 자체를 바꿀 수 있으니 사전등록 후 측정하라. 트리거 - 10-K/공시 cosine, 텍스트 diff 기반 팩터, 특정 엔티티만 유사도가 튀는 이상값, "추출이 잘렸나?", 리브랜드·사명 변경, TF cosine 정규화 제안.
version: 1.0.0
task_types: [research, debugging, data]
triggers:
  - pattern: "문서 쌍 유사도에서 한 엔티티만 비정상적으로 낮을 때"
  - pattern: "텍스트 유사도 신호를 정규화/교정하려 할 때"
category: trap
---

# 텍스트 유사도는 문서 자기 이름에 지배된다

## Problem
bloasis #99 (2026-10-02). JPM 의 10-K 위험요인 rolling cosine 이 S&P 500 최저(0.704).
먼저 의심한 건 추출: FY2025 10-K 가 처음으로 다른 filer-agent 접수번호였고 길이가 −17%.
**틀렸다** — 두 해 모두 Item 1B 직전에서 정확히 끝났다. 원인은 FY2024↔FY2023 쌍(0.4255):

```
FY2023 top tokens: jpmorgan 538, chase 536, ...
FY2024 top tokens: jpmorganchase 533, ...
```

회사가 사명을 붙여 쓰기 시작했고, 자기 이름이 최빈 토큰이라 raw TF cosine 이 무너졌다.
이슈 제목이 가리킨 연도(FY2025)도 틀렸다 — 평균 w2 의 다른 쌍이 범인이었다.

## Solution
1. 이상값이면 **쌍별 cosine 을 전부** 찍어라(rolling 평균은 범인 쌍을 숨긴다).
2. 범인 쌍의 **최빈 토큰 top-8 을 나란히** 찍어라 — 이름 표기 변화는 첫 줄에 보인다.
3. 추출 의심은 "구간 끝 다음 텍스트가 다음 Item 인가"로 1분 안에 확인/기각.
4. 교정(이름 토큰 제거)은 **신호를 바꾼다**: 사전등록(변형·프로토콜·채택 허용폭) 후 측정.
   #99 에선 교정이 JPM 을 고쳤지만(0.43→0.996) 백테스트 α 를 +3.74%→+0.01% 로 지웠다 —
   **측정된 엣지 일부가 이름 빈도에 붙어 있었다.** 미채택으로 기록, 엣지 신뢰도 경고로 승격.
5. 일반 단어(energy, financial, bank…)까지 빼는 넓은 교정은 컷오프 근처 순위를 흔든다 —
   고유 이름 형태(+붙인 형태 `jpmorganchase`)만 빼라.

## Red Flags
- "추출이 잘렸나?"를 구간 경계 확인 없이 가정
- rolling 평균값만 보고 어느 쌍인지 안 쪼갬
- 정확도 교정이라며 사전등록 없이 신호 변경 — 교정이 성과를 지우면 그건 발견이다

## Related
- [[a-qualifying-sweep-arm-must-be-explained-by-its-mechanism]]
- [[a-cache-keyed-by-immutable-input-never-receives-the-parser-fix]]
