---
name: a-lookup-resolved-after-the-full-stream-leaks-the-future
description: 이벤트 로그를 파싱할 때 개체 표(unit/entity table)를 스트림 끝까지 다 만든 뒤 다른 스트림의 참조(tag·id)를 그 표로 해석하면, 참조마다 붙는 속성은 "그 시점 값"이 아니라 "마지막 값"이 된다 — 미래 정보가 사실 계층에 조용히 섞인다(나중에 부서질 포탑이 `TowerDead`로 찍힘). 참조는 그 시점 이하 이벤트로만 해석하고, 절단 검사 + 일부러 새는 대조로 검증하라. 트리거 - 두 스트림(tracker/game, 상태/명령, CDC/요청) 조인, 최종 상태 dict로 과거 이벤트 해석, "type/status/owner"가 나중에 바뀌는 개체, 결정 시점 패킷·피처에 개체 속성 포함, 시간 경계·미래 누출 감사.
version: 1.0.0
task_types: [data-analysis, research, debugging]
triggers:
  - pattern: "resolving references from one event stream against a table built from another, complete stream"
  - pattern: "decision-time features include an entity attribute that can change later"
  - pattern: "future-leak / time-boundary audit of parsed replay or log facts"
---

# 스트림을 다 읽고 만든 조회표는 미래를 흘린다

hots-replay-analysis 2026-10-26 (PR #36 hero entity classification)에서 얻은 교훈.

## 함정

- 파서는 tracker 스트림을 **끝까지** 처리해 `units[tag]`를 만들고, 그 뒤 game 스트림의 명령 대상 tag를 그 표로 해석했다. 표의 `unit_type`은 `SUnitTypeChangeEvent`가 반영된 **최종 유형**.
- 결과: 포탑 L2/L3를 공격한 명령 5,735건이 `TownCannonTowerDead`로 기록돼 판단 패킷(평가자 입력)에 들어감 = "이 포탑은 나중에 부서진다". 메디브 까마귀·알렉스트라자 용 형태 308건도 마지막 형태로 찍혀, 유형 이름으로 플레이어를 찾던 소비자가 상대를 놓침.
- 여러 PR 동안 "판단 시점 경계"를 감사했지만, 감사는 **사실 목록을 시각으로 자르는 것**이었다. 사실 하나의 **필드 값이 미래에서 왔는지**는 아무도 보지 않았다 — 사실의 타임스탬프는 과거였으니까.

## 고친 방법

- 참조 해석을 이벤트 시각 기준으로: tag별 이벤트 이력을 루프 순으로 모으고, 참조 시점 `bisect_right(loops, t)` 이하만, 그것도 **마지막 생성 이후**만 읽는다(tag 재사용 대비). 유형·생존·소유자를 모두 그 슬라이스에서 계산.
- 원래 파서 필드(최종값)는 이력이 없을 때의 호환 fallback으로만.

## 검증 (뒤집힐 수 있는 검사)

1. **절단 검사**: 경기마다 N개 절단점에서 그 이후 이벤트를 전부 버리고 다시 추출 → 절단점 이전 참조의 필드가 전체 추출과 같아야 한다(97경기 442,542건 불일치 0).
2. **새는 대조**: 해석 함수를 "tag의 모든 이벤트를 읽게" 몽키패치해 같은 검사를 돌리면 불일치가 나와야 한다(3,327건). 대조가 0이면 검사가 아무것도 재지 않는 것. [[a-check-that-cannot-flip-is-not-measuring-anything]]
3. 주의: 절단 시 **이미 파싱된 참조 필드(최종값)는 남아 있다** — 그 값을 쓰는 구현은 절단 검사를 통과해 버린다. 그래서 "최종값 vs 시점값이 다른 참조 수"를 따로 세서 누출 규모를 보고했다.

## 적용 방법

- 두 스트림을 조인하는 코드를 보면 "표가 언제 완성되는가, 조회는 언제 일어나는가"를 먼저 묻는다. 조회가 완성 후면, 바뀔 수 있는 속성 목록(type, status, owner, level)을 뽑아 최종값≠시점값 건수를 센다.
- 파서 수정이 재처리를 강제하면(서명 변경), 소비 계층에서 시점 해석을 하고 파서 원값은 보존한다.
