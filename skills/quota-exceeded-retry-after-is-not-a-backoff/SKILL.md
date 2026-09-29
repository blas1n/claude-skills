---
name: quota-exceeded-retry-after-is-not-a-backoff
description: 429 를 전부 "잠깐 기다렸다 재시도"로 처리하면, 주간/월간 쿼터 소진 429 의 Retry-After(= 창이 풀릴 때까지, 수십만 초)를 그대로 sleep 해서 배치 잡이 타임아웃까지 멈춘다. 레이트리밋 429 와 쿼터 429 를 **본문 코드/헤더로 구분**하라. 트리거 - HTTP 클라이언트의 429 재시도 로직, Retry-After 존중, 유료 API 주간 한도, cron/Actions 수집 잡, "잡이 왜 몇 시간째 안 끝나지".
---

# quota_exceeded 의 Retry-After 는 백오프가 아니다

## Problem
hpgg 수집기(Heroes Profile API v1)는 429 면 `Retry-After` 만큼 자고 한 번 재시도했다.
- 증상(잠복): 쿼터가 없는 동안은 드러나지 않음. 소진되는 순간 GitHub Actions 잡이 멈춤.
- 근본 원인: 같은 429 라도 `{"error":{"code":"quota_exceeded"}}` 의 Retry-After 는 **롤링 7일 창의 리셋까지 남은 초**(실측 ~578,000 s ≈ 6.7일). 레이트리밋(분당) 429 와 의미가 다르다. `X-HP-Quota-Reset` 도 타임스탬프가 아니라 **남은 초**였다.
- 흔한 오해: "Retry-After 를 존중하는 게 정석" — 짧은 레이트리밋에만 맞는 말.

## Solution
1. 429 본문 코드(또는 쿼터 헤더 `X-*-Quota-Remaining == 0`)로 쿼터 소진을 구분한다.
2. 쿼터 소진 → **즉시 포기**하고 호출자에 명시적 결과로 돌려준다(이전 데이터 유지, 로그에 remaining/reset). 재시도 금지.
3. 레이트리밋 429 → 상한(예: 120 s)을 둔 백오프만 허용. 상한을 넘는 Retry-After 는 쿼터로 간주.
4. 매 응답의 `*-Quota-Remaining` 을 로그에 남겨(`hp.quota`) 소진을 미리 본다. 서버라면 floor(예: 200) 아래에서 라이브 호출을 끄고 캐시로 degrade.

## Key Insights
- 재시도 로직은 **대기 시간의 상한**이 없으면 외부 값이 내 잡의 수명을 정한다.
- "헤더 이름이 Reset" 이라고 타임스탬프라고 가정하지 말고 실제 값을 한 번 찍어 보라.

## Red Flags
- `await asyncio.sleep(int(resp.headers["Retry-After"]))` 에 상한이 없음
- 한도가 주/월 단위인 유료 API
- 스케줄 잡이 가끔 타임아웃으로만 실패
