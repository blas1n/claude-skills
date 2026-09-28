---
name: keep-previous-data-mixes-two-views-facts
description: 새 뷰를 불러오는 동안 이전 결과를 화면에 남기는(keepPreviousData·placeholderData·"dim the old table") UI 는, 라벨·필터 상태는 새 state 에서, 숫자는 옛 데이터에서 읽어 **두 뷰의 사실을 한 문장에 섞는다**. 표에 딸린 사실(패치·표본·갱신일)은 반드시 같은 모델에서 읽거나 로딩 중엔 가려라.
---

# Keeping the previous data while loading mixes two views' facts

## Problem

- 증상 (hpgg 티어표, 2026-09-29): 빠른 대전 → 폭풍 리그 전환 시 새 스냅숏을 받는 동안 이전 표를 흐리게 남겼다.
  제목 줄이 `폭풍 리그 · 전체 전장 · 패치 … · 50,280 매치` — **모드 라벨은 새 state, 매치 수는 옛 표(빠른 대전)**.
  수백 ms 짜리 거짓 문장이라 눈으로는 거의 안 보인다.
- 발견 경위: e2e 가 클릭 직후 `getAttribute("data-tier")` 를 **재시도 없이** 읽다가 옛 값 "B" 를 받고 실패했다.
  레거시 구현은 데이터가 올 때까지 컨트롤 자체를 안 바꿔서 이 창이 없었다 — 재작성하며 "이전 표 유지"를 넣는 순간 생겼다.
- 근본 원인: 한 줄의 사실들이 **서로 다른 출처**(state vs 로드된 모델)에서 조립된다. keepPreviousData 는 모델만 옛 것으로 유지한다.
- 흔한 오해: "흐리게(opacity) 했으니 사용자는 로딩 중인 걸 안다" — 텍스트는 흐려도 읽히고, 스크린샷·스크린리더엔 그대로 남는다.

## Solution

1. 표에 딸린 사실(패치, 표본 수, 갱신일, 구간/전장 이름)을 **모델에 넣고** 모델에서만 읽어라 (`table.patch`, `table.matches`, `table.collectedAt`).
2. 로딩 중(`computed === null`)엔 그 줄을 `불러오는 중…` 으로 바꾸고 표엔 `aria-busy="true"`.
3. 테스트는 로딩 창을 **결정적으로** 만들어 고정: 라우트를 붙잡고(`page.route(url, async r => { await held; r.continue() })`) → 로딩 문구·`aria-busy=true` 단언 → 풀고 → `aria-busy=false`. 붙잡지 않으면 로컬 fetch 가 첫 폴링보다 빨라 플레이키해진다.
4. 전선 절단: 로딩 분기를 끊고 테스트가 **정확히 그 거짓 문장**(옛 매치 수 + 새 라벨)으로 빨개지는지 본다.

## Key Insights

- 재시도 없는 속성 읽기(`getAttribute`) 테스트가 레이스로 실패하면, 테스트를 `expect.poll` 로 고치기 전에 **그 중간 상태가 사용자에게 무엇을 말하는지** 먼저 봐라. 이번엔 테스트 플레이크가 아니라 제품 결함이었다.
- "이전 결과 유지"는 공짜 UX 개선이 아니다 — **어떤 텍스트가 어느 출처에서 오는지** 표를 그려라.

## Red Flags

- `last.current = computed; const table = computed ?? last.current` 류 코드
- 라벨/셀렉트는 state, 숫자는 fetched data 에서 읽는 헤더·요약 줄
- 전환 직후 읽는 e2e 가 가끔 이전 값
