---
name: a-gap-list-by-name-pattern-mixes-misses-with-correct-rejections
description: "이름이 X처럼 보이는데 분류기가 X라고 안 한 것"을 세어 만든 누락 목록(예 - `Hero*` 유형인데 hero가 아님 2.6%)은 진짜 누락과 **올바른 거부**가 섞여 있다. 이름이 같은 다른 개체(복제·소환·형태)가 있기 때문이다. 누락이라 부르기 전에 소유자·컨트롤러·생명주기 같은 관계 필드로 유형을 분해하라 — 이전 보고서의 "Artanis 분류 누락"은 Abathur가 만든 Artanis 복제였다. 트리거 - 접두사/정규식 기반 갭 카운트, "분류기가 놓친 N건" 보고, 누락률을 0%로 만드는 수정 요청, 같은 유형 이름이 여러 소유자에게 있는 데이터, 이전 연구의 진단을 이어받을 때.
version: 1.0.0
task_types: [research, data-analysis, eval]
triggers:
  - pattern: "a gap count built from a name/prefix pattern the classifier did not accept"
  - pattern: "inheriting a previous report's 'classifier missed X' diagnosis"
  - pattern: "request to drive a miss rate to zero"
---

# 이름 패턴으로 만든 누락 목록은 누락과 올바른 거부를 섞는다

hots-replay-analysis 2026-10-26 (PR #36)에서 얻은 교훈.

## 함정

- PR #35: 본인 명령 대상이 `Hero*` 유형인데 `target_category != hero`인 2,866건을 "영웅 분류 누락"으로 보고. 대표 사례 e11 = "Artanis 대상 명령 3개 누락".
- 분해해 보니(대상 유닛의 생성 컨트롤러 vs 로스터): D.Va 메카·바이킹·첸 분신 2,598건은 진짜 누락(그 플레이어 영웅의 형태·개체), **268건은 Abathur 궁극기 복제** — 다른 플레이어(Abathur)가 생성·조종하는, 아군 영웅 유형 이름의 유닛. e11의 3개도 복제였다. 진짜 Artanis 대상 명령은 원래부터 hero였다.
- "누락 0%"를 목표로 `Hero*` 접두사 승격을 했다면 268건을 엉뚱한 플레이어의 영웅 교전으로 만들었고, e11 같은 사례를 잘못 "해결"했을 것이다.

## 분해 방법

1. 갭 행마다 관계 필드를 붙인다: 소유/컨트롤러(생성 이벤트), 그 소유자의 정체(로스터), 스냅숏의 컨트롤러, 생성·소멸 시점과 참조 시점.
2. `(이름, 소유자 관계)`로 집계: 소유자 자신의 것 / 다른 로스터 개체의 이름 / 소유자가 로스터에 없음. 첫 표만 봐도 원인이 갈린다.
3. 각 묶음마다 원본 근거(생명 = 사망 이벤트 수 대조 등)를 확인한 뒤에만 승격. 근거 없는 묶음은 `unknown`, 다른 개체의 이름을 단 것은 명시적 `copy`로 기록(거부도 사실로 남긴다).
4. 이전 보고서의 진단은 가설로 취급하고 대표 사례 하나를 원본 이벤트까지 추적해 확인한 다음 인용한다.

## 적용 방법

- "분류기가 놓친 N건"을 받으면 성공 지표를 "N→0"이 아니라 "N을 원인별로 분해하고, 원본이 뒷받침하는 것만 승격, 잘못된 승격 0"으로 바꾼다.
- 보고서에는 승격 수와 함께 **명시적으로 거부·분리한 수**를 같은 표에 둔다.
