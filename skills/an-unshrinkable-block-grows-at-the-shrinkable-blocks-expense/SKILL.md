---
name: an-unshrinkable-block-grows-at-the-shrinkable-blocks-expense
description: 응답이 고정 바이트 예산 안에서 "줄이지 않는 블록을 먼저 채우고 남은 예산에 줄일 수 있는 블록을 맞추는" 구조면, 줄이지 않는 블록에 필드를 추가해도 한도 초과·테스트 실패는 거의 안 난다 — 대신 줄일 수 있는 블록(map_window 등)이 조용히 줄고, 일부 요청만 response_too_large로 넘어간다. 특히 항목마다 붙는 메타데이터가 거의 전부 기본값(unknown/null)이면 정보 0인 바이트가 예산을 먹는다. 센서는 "한도 안인가"가 아니라 실데이터 전수에서 main 대비 축소 블록 포함 비율·실패 수의 차이다. 트리거 - max_response_bytes, 60KB 예산, 응답에 per-item 블록/필드 추가, reductions·map_window_omitted, "줄이지 않는다" 규칙, 리뷰에서 "응답이 커질 수 있다"를 가능성으로만 남김.
---

# 줄이지 않는 블록은 줄일 수 있는 블록의 몫으로 자란다

## Problem

- PR #63(hots hero focus): `inputs`에 `ability_identities`(입력마다 식별 객체)와 `ability_attempts`(입력 묶음, id 반복)를 추가. 단위 테스트·합성 픽스처·크기 한도 assert 모두 초록.
- 리뷰는 "60초 창에서 response_too_large가 날 수도"를 *가능성*으로만 남겼다. 응답은 언제나 59.9 KB 근처로 꽉 차 있었다(§6 최대 59,896 B) — 즉 **여유는 이미 0이고 남는 바이트는 전부 map_window가 먹고 있었다.**
- 실데이터 전수(397경기 사망 14,100건 × 창 3종, main 모듈과 PR 모듈 나란히)에서:
  - 30/15: map_window 포함 비율 중앙값 1.00 → 0.70, 생략 63 → 742
  - 45/15(60초): response_too_large 8 → 344
- 원인: store의 능력 입력 ~100만 건 중 `mapping_status=confirmed`는 326건(0.03%). 식별 객체는 99.97%가 `null·unknown` 반복. 최악 사례에서 두 블록 25.9 KB > 기존 `inputs.rows` 17.8 KB.

## Solution

1. **측정 먼저**: `git show main:path/module.py > scratch/basefocus.py`로 기준 모듈을 따로 import해 같은 입력에 두 버전을 돌린다(multiprocessing은 파일 모듈이어야 pickle 됨). 상태(ok/too_large), reductions 종류, 축소 블록 포함 비율, 블록별 바이트를 기록하고 **차이**를 본다.
2. **분포를 센다**: 새 메타데이터 필드 값 분포(`grep -o '"mapping_status":"[a-z_]*"' | sort | uniq -c`). 한 값이 지배적이면 그게 기본값이다.
3. **기본값은 한 번만**: `unlisted: {...기본값}` + `unlisted_rule`, 예외만 행으로. 블록 수준 상수(`execution: unknown`)는 블록에 한 번.
4. **열 형식**: 반복 dict 키 대신 `columns` + `rows`(기존 `inputs.rows`와 같은 관례). 다른 블록으로 조인 가능한 값(ability_id)은 중복 저장하지 않는다.
5. 회귀 테스트: "N개 입력 창에서 새 블록 바이트 ≤ k·N" — 한도 assert가 아니라 **추가분의 상한**.
6. 결과: 30/15 중앙값 0.91(main 1.00), 60초 실패 14(main 8, PR 원본 344). 남은 차이는 문서에 수치로 기록.

## Key Insights

- 예산 구조에서 "줄이지 않는다"는 "공짜다"가 아니다. 비용은 실패가 아니라 **다른 블록의 손실**로 나타나므로 초록 테스트로는 안 보인다.
- 한도 근처에 늘 붙어 있는 응답(최대치 ≈ 한도)은 여유가 0이라는 신호 — 추가 바이트 = 축소 블록 손실 1:1.
- per-item 메타데이터를 넣기 전에 값 분포를 본다. 지배 값은 기본값으로 접는다.
- 리뷰의 "가능성" 지적은 실데이터 전수 비교 한 번이면 확정/기각된다. 합성 픽스처는 분포(99.97% unknown)를 재현하지 못한다.
- 커밋된 실응답 표본 갱신은 [[a-golden-response-under-a-byte-budget-cannot-be-patched]] (사례 고정, 응답만 재생성).
