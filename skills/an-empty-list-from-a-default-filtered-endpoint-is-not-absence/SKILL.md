---
name: an-empty-list-from-a-default-filtered-endpoint-is-not-absence
description: 공개 API 가 `[]` 를 돌려줬다고 "없다 / 거절됐다 / 저장 안 됐다"로 판정하면 안 된다 — 많은 목록 엔드포인트는 **기본값으로 걸러서** 돌려준다(승인된 것만, 특정 종류만, 캐시된 카드용만). 빈 목록은 "그 필터를 통과한 게 없다"일 뿐이다. 결론을 사람에게 행동(재업로드·재시도)으로 넘기기 전에 ① 필터 해제 플래그로 다시 묻고 ② 소유자 콘솔(Creator Hub·대시보드)의 상태와 맞춰 보라. 트리거 - 외부 플랫폼 심사/게시 상태를 공개 API 로 폴링, "media list `[]`", "아직 안 올라갔다", 사람에게 "다시 올려달라" 고 하기 직전, 카드/썸네일이 기본 이미지로 나옴, Roblox games/thumbnails API.
version: 1.0.0
task_types: [debugging, evaluation, ops]
category: trap
---

# 기본 필터가 걸린 엔드포인트의 빈 목록은 부재가 아니다

## 실제 사례 (BSPlay / Frostwisp, 2026-10-07 → 10-27)

Roblox 게임 썸네일 게시 여부를 공개 API 로 쟀다.

- `GET games.roblox.com/v2/games/{universe}/media` → `{"data":[]}`
- 10-07 에 이걸 "심사 중도 아니다 — 거절됐거나 저장 안 됨"으로 판정하고 체크리스트에 적고, 사람에게 **재업로드를 요청**했다.
- 3주 동안 같은 센서로 "아직 안 됨"을 반복 보고.
- 사람이 Creator Hub 스크린샷을 보냄: 썸네일 **활성**.
- 같은 엔드포인트에 `?fetchAllExperienceRelatedMedia=true` → `imageId …, approved: true`. 이미지를 내려받아 보니 우리 썸네일.

센서가 처음부터 우리 질문("승인된 미디어가 있는가")에 답할 수 없는 조회였다.

## 같은 세션의 형제 함정

1. **ID 종류 혼동.** 체크리스트에서 긁은 10자리 숫자(사용자 id)를 placeId 로 넣었더니 엉뚱한 universe 가 나와 `[TITLE UNAVAILABLE]`. 숫자만 보고 ID 를 집지 말고 **그 숫자가 적힌 문맥(`user=`, `placeId`)** 을 확인.
2. **신호 단계 분리.** 미디어 승인(`approved:true`) 뒤에도 게임 카드 엔드포인트(`thumbnails/v1/games/multiget/thumbnails`)는 한동안 기본 이미지(`980ef4…` 해시)를 준다. "승인됨"과 "카드에 노출됨"은 별개의 체크 항목이다. 기본 이미지 해시는 존재하지 않는 id 에 같은 질문을 던져 얻어 두면 비교 기준이 된다.

## 규칙

1. 빈 목록을 받으면 결론 전에 **그 엔드포인트의 필터 파라미터**(include_all / fetchAll / status / visibility / includeHidden)를 문서에서 찾는다. 없으면 "무엇을 걸러낼 수 있는가"를 적어도 한 번 추정하고 그 플래그를 시도한다.
2. **양성 대조**: 같은 조회가 "있음"을 낼 수 있는지 한 번 보여라 — 이미 존재가 확실한 항목(예: 승인된 아이콘, 다른 게임의 미디어)에 같은 조회를 던진다. 거기서도 `[]` 면 센서가 틀린 것.
3. 사람에게 **비용이 드는 행동**(재업로드, 재제출, 문의)을 요청하기 전엔 소유자 콘솔 상태를 먼저 물어 맞춘다. 공개 API 는 소유자 화면의 지연·필터된 그림자다.
4. 기록에 센서 자체를 적는다(엔드포인트 + 파라미터 + "live"의 판정식). 다음 사람이 같은 `[]` 를 같은 결론으로 읽지 않게.

관련: [[absence-measurement-validity-check]] (생산자가 꺼진 경우), [[a-failed-read-degraded-to-empty-becomes-a-measurement]] (실패가 빈값으로 바뀐 경우), [[a-check-that-cannot-flip-is-not-measuring-anything]].
