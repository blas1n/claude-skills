---
name: an-upstream-refusal-degraded-to-stale-serves-what-it-refused
description: 캐시 앞단의 "업스트림이 실패하면 stale 캐시를 보여준다" 폴백은 **모르는 4xx 를 전부 장애로** 접는다 — 그런데 업스트림이 일부러 거절하는 경우(비공개 전환·삭제·차단·권한 회수·법적 삭제)엔, 그 폴백이 **거절당한 바로 그 데이터를** "잠시 오래된 정보" 딱지를 붙여 계속 서빙한다. 테스트·로그는 전부 "우아한 degrade" 로 읽힌다. 거절 코드를 **실측해서** 장애와 분리하고, 거절이면 캐시를 지우고 다시 묻지도 마라. 트리거 - stale-while-error/serve-stale 폴백, `else: return degraded(stale)`, 외부 API 의 개인정보·프라이버시·takedown 조항, "403 은 일단 unavailable 로", 프로필/사용자 데이터 캐시.
version: 1.0.0
task_types: [bugfix, review, coding]
---

# 업스트림의 거절을 stale 폴백으로 접으면, 거절당한 데이터를 서빙한다

## Problem

외부 API 캐시 서비스의 흔한 모양:

```python
if up.status == 200: cache + return
if up.status == 404: return not_found
if up.status == 429 and up.code == "quota_exceeded": return degraded(stale, "quota")
log.warning("upstream_unavailable", status=up.status)
return degraded(stale, "upstream_unavailable")   # ← 모르는 건 전부 여기로
```

`degraded(stale)` 는 캐시가 있으면 **옛 프로필을 stale 표시와 함께** 돌려준다. 5xx·타임아웃엔 옳다.

그런데 업스트림이 **의도적으로** 거절하는 상태가 있다. 실측(Heroes Profile, 2026-10-01):

```
GET /players?battletag=<비공개 전환한 플레이어>  →  403 {"code":"player_unavailable",
                                                       "message":"That player has made their profile private."}
GET /players?battletag=<없는 플레이어>           →  404 player_not_found
```

403 은 위 분기에서 "모르는 에러" → `upstream_unavailable` → **비공개로 숨긴 프로필을 캐시에서 꺼내 보여줌.**
약관(§5: 비공개 전환 24 h 안에 모든 표면·캐시에서 제거)을 정면으로 위반하는데, 모든 신호가 정상이다:
테스트 초록, 로그는 `upstream_unavailable` 경고 한 줄, UI 는 "잠시 오래된 정보" 배너 — 설계대로 동작하는 것처럼 보인다.

또 하나: 캐시 TTL 은 "신선함"만 제한하고 stale 서빙엔 **상한이 없었다.** 쿼터가 바닥난 주엔 며칠 전 데이터가 무기한 나간다.

## Detect

- 폴백 분기가 `else`/기본값으로 끝나고, 그 분기가 stale 을 서빙한다
- 401/403/410/451 같은 "의도적 거절" 코드를 분기에서 따로 다루지 않는다
- stale 서빙 경로에 나이 상한(`now - fetched_at`)이 없다
- 외부 API 약관에 privacy/takedown/deletion 조항이 있다

## Fix

1. **업스트림 거절 코드를 실측하라** — 문서보다 실제 응답. 피드·목록에서 해당 상태인 실제 대상을 하나 골라 한 번 호출한다(에러는 보통 과금 안 됨).
2. 거절 코드를 장애보다 **먼저** 분기한다: 거절 → 캐시 행 삭제 + "거절됨" 상태 기록 + 전용 응답(`403 player_private`). 이후 조회는 업스트림에 다시 묻지도 않는다.
3. stale 서빙에 **나이 상한**을 둔다 (`stale_max_seconds`, 규정 시한 이하). 주기 작업이 그보다 오래된 행을 지운다 — 거절 신호(피드)가 죽어도 규정을 넘지 않게.
4. 캐시 키가 사용자 입력 철자 그대로면(대소문자) 삭제는 **정규화해서** 매칭한다 — 한 사람이 여러 키로 남아 있다.

## Test

- 캐시 → TTL 경과 → 업스트림이 기록된 거절 응답 → 결과가 `private` 이고 프로필 없음, 캐시 행 삭제, 두 번째 조회에 업스트림 호출 없음. **이 테스트는 고치기 전 `ok`(stale) 로 빨개져야 한다** — 그게 결함의 증거.
- stale 상한 초과 + 쿼터 소진 → stale 이 아니라 `quota_exceeded`.

## Related

- [[a-failed-read-degraded-to-empty-becomes-a-measurement]] — 같은 계열: 실패를 접는 기본값이 의미를 바꾼다. 거기선 `[]` 가 "없음"을 주장하고, 여기선 stale 이 "아직 있음"을 주장한다.
- [[status-code-is-not-a-reason-code]] — 403 하나에 여러 이유. `code` 로 분기하라.
