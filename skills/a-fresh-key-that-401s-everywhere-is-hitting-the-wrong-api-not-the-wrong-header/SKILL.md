---
name: a-fresh-key-that-401s-everywhere-is-hitting-the-wrong-api-not-the-wrong-header
description: 방금 발급한 API 키가 모든 엔드포인트에서 401 이면, 헤더·쿼리 이름을 바꿔 가며 클라이언트를 고치지 마라. 발급자 대시보드의 **Last Used** 와 내비게이션의 **Migrating / v1** 링크부터 봐라 — 문서 사이트가 폐기된 API 를 가리키고 새 키는 새 호스트에서만 산다. 트리거 - 새 키 401·403, `docs.` 또는 `api.` 서브도메인 문서, 가짜 키와 진짜 키의 응답이 같을 때, "Last Used: Never", 대시보드에 Migrating·Legacy·v1·v2 메뉴.
version: 1.0.0
task_types: [debug, integration]
triggers:
  - pattern: "새로 만든 API 키가 401/Unauthenticated"
  - pattern: "인증 헤더·쿼리 파라미터 이름을 여러 개 시도하고 있다"
  - pattern: "벤더 사이트에 Migrating·Legacy·Deprecated·v1 메뉴가 있다"
category: trap
---

# 새 키가 모든 곳에서 401 이면 헤더가 아니라 호스트가 틀렸다

## Problem

- 증상: 결제·발급 직후의 API 키로 `?api_token=`, `Authorization: Bearer`, `X-Api-Key`, `api_key=` … 일곱 가지를 돌려도 전부 401. 일부러 넣은 **가짜 키와 응답이 완전히 같다**.
- 근본 원인: 문서 사이트(`api.heroesprofile.com/docs`)가 **폐기 예정인 옛 API** 를 설명하고 있었고, 새 키는 새 호스트(`www.heroesprofile.com/api/external/v1`) + Bearer 에서만 유효했다. 옛 호스트는 새 키를 모르므로 어떤 인증 형태로 보내도 "키 없음"이다.
- 흔한 오해: 401 을 "내 전송 방식이 틀렸다"로 읽고 클라이언트 쪽 변수를 돌린다. 하지만 **가짜 키와 진짜 키가 같은 응답**이면 서버가 키를 "검사하고 거부"한 게 아니라 **애초에 대조할 대상이 없는** 것이다.

## Solution

1. **먼저 발급자 쪽을 읽어라.** 대시보드 API Keys 표의 `Last Used`. `Never` 면 어떤 요청도 그 키로 인증된 적이 없다 — 클라이언트 변형은 전부 헛수고였다는 증거.
2. **대조군 한 번**: 가짜 키로 같은 요청. 응답이 동일하면 인증 *방식* 문제가 아니라 인증 *대상(호스트/버전)* 문제.
3. **내비게이션에서 Migrating / v1 / Legacy 를 찾아라.** 그 페이지가 진짜 계약이다: base URL, 헤더 방식, 응답 봉투, 무엇이 무료인지.
4. 새 base URL 로 **가장 싼 엔드포인트**(목록·메타데이터)를 먼저 쳐서 200 을 확인한 뒤 본 엔드포인트로.
5. 발견한 이사 사실을 설계 문서·메모리에 적어라 — 옛 문서 URL 은 검색 결과 상위에 계속 남는다.

## Key Insights

- 401 은 "키를 봤는데 틀렸다"와 "키를 볼 줄 모른다"를 구분하지 않는다. 구분하는 건 **가짜 키 대조군**과 **발급자 측 Last Used** 뿐이다.
- 벤더의 문서 서브도메인은 이사 후에도 오래 살아 있다(이 건은 2027-01 종료 예고). "문서에 그렇게 써 있다"는 옛 표면의 문장일 수 있다.
- 헤더 변형을 N 번 시도하는 비용은 작아 보이지만, 그 시간 동안 **가설이 '내 코드'에 고정**된다. 두 번째 401 에서 멈추고 반대편 끝을 읽어라([[a-timeout-names-the-waiter-not-the-cause-read-the-other-end]] 와 같은 모양).

## Red Flags

- 새 키인데 `Last Used: Never`
- 가짜 키와 진짜 키의 상태 코드·본문이 같다
- 대시보드 상단 메뉴에 `Migrating`, `Legacy`, `v1`, `Deprecated` 가 있다
- 문서의 인증 예시가 쿼리스트링 토큰(`?api_token=`)인데 대시보드는 "Bearer" 를 말한다
- `Accept: application/json` 을 붙이면 302→로그인이 401 JSON 으로 바뀐다(인증 게이트 뒤라는 뜻, 결함 아님)
