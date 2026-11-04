---
name: a-golden-response-under-a-byte-budget-cannot-be-patched
description: API 응답이 바이트 상한 안에서 어떤 블록을 줄이는(축소·생략·페이지) 규칙을 갖고 있으면, 다른 블록에 필드 하나만 추가해도 줄어드는 블록의 범위가 바뀐다 — 그래서 커밋된 골든 응답(실제 운영 응답 표본)에 새 필드만 덧대면 "운영이 실제로 줄 응답"과 다른 거짓 표본이 된다. 또 규칙으로 사례를 고르는 표본 생성기를 커진 코퍼스에서 다시 돌리면 무관하게 사례가 바뀐다. 트리거 - 골든/스냅숏 응답 비교 테스트가 새 필드 때문에 실패, max_response_bytes·60KB 상한, map_window 축소, reductions/continue_with, make_samples 재실행, 표본 재생성, 응답에 객체 추가.
---

# 바이트 예산 아래의 골든 응답은 덧댈 수 없다

## Problem

- 상황: 사망 항목에 `killing_blow` 객체를 추가했더니 `test_matches_the_store_response`(커밋된 운영 응답 = 리플레이 재구성)가 5사례 전부 실패.
- 첫 생각: "표본 JSON의 `deaths_in_range`에 같은 객체만 끼워 넣으면 된다." 틀렸다.
  - 응답은 60 KB 예산 안에서 `map_window`를 줄인다. 객체가 늘어난 만큼 3/5 사례의 `map_window` 범위·`reductions`·이어받기 창이 바뀌었다(904.2–920.0 → 905.5–919.3초). 덧댄 표본은 새 서버가 절대 주지 않는 응답이고, 브라우저 E2E에 박힌 창 경계 문자열도 낡는다.
  - 비교 테스트가 일부 키만 비교하면(focus·deaths_in_range…) 덧댄 표본도 초록이 된다 → 줄어든 블록의 거짓은 테스트로 안 잡힌다.
- 두 번째 함정: 표본 생성기(`make_samples.py`)를 그대로 다시 돌리니, 표본 작성 뒤 동기화된 새 경기 때문에 "가장 많은 동시 사망" 사례가 **다른 경기로 바뀌었다**. 변경과 무관한 사례 교체가 diff에 섞인다.

## Solution

1. 운영 store를 APFS 복제(`cp -c -R`, 수 초)하고 새 코드로 재처리한다(배포 전체 재처리 리허설 겸).
2. 기존 index의 (경기, 플레이어, t)를 **고정**하고 생성기와 같은 도구 호출만 다시 한다 — 선택 규칙은 재실행하지 않는다.
3. 키별로 diff를 분해해 "의도한 필드 추가 + 예산 때문에 줄어든 블록"만 바뀌었는지 확인한다(`{k for k in old|new if old[k]!=new[k]}`, 새 필드를 뺀 항목 == 이전 항목).
4. 하드코딩된 경계 숫자(E2E 문자열, 문서)를 grep해 갱신한다.
5. 브라우저 E2E가 문서 스크린샷을 덮어쓰면 범위 밖이므로 `git checkout`.

## Key Insights

- 응답에 크기 예산 규칙이 있으면 **모든 블록은 서로 결합**돼 있다. 필드 추가는 그 필드 블록만의 변경이 아니다.
- 골든 표본은 "생성 경로를 다시 실행한 결과"여야지 "손으로 고친 결과"이면 안 된다. 생성 경로에 필요한 원본(store)이 무겁다면 CoW 복제로 싸게 만든다.
- 규칙 기반 사례 선택기는 코퍼스가 자라면 결과가 바뀐다. 재생성은 선택과 생성을 분리해 선택을 고정한다.
- 관련: 재처리 배치가 도는 중에 캐시 지문에 포함된 소스 파일을 고치면 앞/뒤 경기의 시그니처가 섞인다 — 배치를 멈추고 코드를 확정한 뒤 다시 시작한다(완료분은 같은 시그니처면 건너뜀). [[a-cache-keyed-by-immutable-input-never-receives-the-parser-fix]]

## Case: CI가 skip해서 표본 불일치가 PR에 실려 감 (PR #63, 2026-11-04)

- `inputs`에 새 키를 추가한 PR이 표본을 갱신하지 않았는데 CI는 초록 — `test_hero_focus_real`/`test_tactical_real`은 리플레이가 없으면 skip. 로컬(리플레이 동기화된 워크트리)에서만 실패.
- 응답 블록에 키를 추가하는 PR은 리뷰 시 **로컬에서 실데이터 테스트를 직접 돌려** skip이 아닌지 확인한다. 전술 표본(`make_tactical_sample.py`)은 운영 id secret이 필요 — `main/.env`의 `HOTS_MCP_ID_SECRET`만 export(값 출력 금지), sha 일치로 같은 경기 확인.
- 축소 경계가 바뀌면 `docs/TACTICAL_MAP.md` §4의 구간 이력도 갱신.
- 관련: [[an-unshrinkable-block-grows-at-the-shrinkable-blocks-expense]]
