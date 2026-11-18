---
name: goatcounter-api-pagination-and-rate-limit
description: GoatCounter API(/api/v0/stats/*)로 방문 통계를 모을 때 — /stats/hits 페이지 넘김의 exclude_paths는 반복 파라미터(httpx 리스트 기본 인코딩)로 보내면 조용히 무시돼 같은 페이지가 계속 오고, 초당 4회 제한을 넘으면 429 대신 연결을 끊는다. 트리거 - GoatCounter 통계 수집 스크립트, "more": true가 끝나지 않음, RemoteProtocolError "Server disconnected", 페이지별 합계가 중복으로 부풀어 보임.
---

# GoatCounter API: exclude_paths는 쉼표로, 요청은 간격을 두고

## Problem

- 증상 1: `/stats/hits?limit=100`에 이미 받은 path_id를 `exclude_paths`로 넘기며 다음 페이지를 요청했는데, 1위
  페이지가 다시 나오고 `"more": true`가 끝나지 않는다. 합계가 중복으로 부풀거나 루프가 안 끝난다.
- 증상 2: 몇 번 연달아 요청하면 `httpx.RemoteProtocolError: Server disconnected without sending a response`.
- 근본 원인:
  - httpx에 `params={"exclude_paths": [1, 2, 3]}`를 주면 `exclude_paths=1&exclude_paths=2…`로 보낸다. GoatCounter는
    이 형식을 무시한다. **쉼표로 이은 한 값**(`exclude_paths=1,2,3`)만 적용된다.
  - 요청 제한은 초당 4회다(`x-rate-limit-limit: 4`). 넘기면 429를 주는 대신 소켓을 닫기도 한다.
- 흔한 오해: "서버가 불안정하다" / "토큰 권한 문제다". 첫 요청은 항상 성공해서 원인이 안 보인다.

## Solution

1. 페이지 넘김: `exclude_paths=",".join(map(str, seen_ids))`. 그리고 새로 받은 항목이 0개면 `more`와 상관없이
   멈춘다(무한 루프 안전장치).
2. 모든 요청 사이에 0.3초 이상 간격을 두고, `TransportError`나 429면 점점 길게 기다렸다 몇 번 재시도한다.
3. 범위는 `start`/`end`에 날짜가 아닌 RFC3339(`2026-09-28T00:00:00Z`)로 준다. 날짜만 주면 `{"error": "not found"}`.
4. `count`는 "한 방문에서 그 페이지를 본 횟수(쿠키 없음)"다. 사이트 전체 순방문자 수가 아니니 보고할 때
   "페이지 방문"이라고 쓴다.

## Key Insights

- 쿼리 배열의 인코딩 방식(반복 vs 쉼표)은 API마다 다르고, 틀려도 에러 없이 무시된다. "결과가 줄지 않는다"를
  센서로 삼는다: 두 번째 페이지의 첫 항목이 첫 페이지에 있었으면 제외 파라미터가 안 먹은 것이다.
- `/api/v0/me` 같은 엔드포인트는 계정 이메일을 그대로 돌려준다. 디버깅 출력에 찍지 않는다.

## Red Flags

- 페이지 루프가 예상보다 오래 돈다, 페이지별 경로 수 합이 사이트 페이지 수보다 크다
- 연속 요청 몇 번째에서 연결이 끊긴다
- 날짜 범위를 줬는데 `not found`
