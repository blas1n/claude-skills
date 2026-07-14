---
name: half-wired-subsystem-audit
description: 서브시스템의 "보이는 절반"(설정 UI·스키마·워커·읽기 엔드포인트)만 만들어지고 "안 보이는 절반"(프로덕션 producer/consumer, authoring 입력구, 서버 승격)이 빠지는 반복 결함. 유닛테스트 100% green으로 통과하며, 자율성은 전부 그 안 보이는 절반에 산다. 신규 서브시스템 설계·리뷰 시, 그리고 "설정은 있는데 왜 동작 안 하지" 증상에서 사용.
version: 1.0.0
task_types: [review, debug, architecture]
required_tools: [Bash, Read, Grep]
triggers:
  - pattern: "설정/스위치는 있는데 아무 일도 안 일어남"
  - pattern: "워커는 도는데 처리할 게 안 들어옴"
  - pattern: "기능이 완성돼 보이는데 프로덕션에서 침묵함"
  - pattern: "자율 파이프라인/스케줄러/알림/큐 서브시스템 설계 또는 리뷰"
---

# Half-Wired Subsystem: 보이는 절반만 만들어진다

## Problem

기능이 완성돼 보인다. 스키마 있고, 설정 UI 있고, 워커 등록돼 있고, REST/MCP 엔드포인트 있고, 유닛테스트 100% green. **그런데 프로덕션에서 아무 일도 일어나지 않는다.**

- **증상**: 스위치를 켜도 무반응 / 워커는 폴링하는데 큐가 영원히 비어 있음 / 상태머신의 terminal state가 한 번도 관측되지 않음 / "설정했는데 알림이 안 와요"
- **근본 원인**: 서브시스템의 **한쪽 끝을 잇는 프로덕션 호출자가 0개**다. 죽은 코드가 완성품처럼 보인다.
- **흔한 오해**: "구현됐고 테스트도 통과하니 동작한다." → 유닛테스트는 그 메서드를 **직접 호출**한다. 프로덕션 경로가 그걸 부르는지는 검증하지 않는다.

### 왜 하필 이 절반이 빠지는가

**구현 압력은 가시성을 따라간다.**

| 절반 | 압력 | 결과 |
|---|---|---|
| 설정 UI, 그리드, 배지, 읽기 API | 디자이너가 보고, 스크린샷 찍히고, 리뷰어가 클릭함 | ✅ 만들어짐 |
| emitter, sweeper, authoring 입력구, 서버 승격 | 아무도 스크린샷 안 찍음. 유닛테스트는 클래스를 직접 호출해서 우회함 | ❌ 빠짐 |

그래서 **UI가 없고 테스트 압력도 없는 절반**이 정확히 빠진다.

**에이전트/자율 시스템에서 이게 치명적인 이유**: 자율성은 전부 그 안 보이는 절반(스케줄러, emitter, resolver, worker, 트리거)에 산다. 시스템이 완성돼 보이면서 **스스로 아무것도 못 하는** 상태가 된다.

---

## 다섯 가지 형태

실증 사례(BSVibe, 2026):

| # | 형태 | 실제 사례 |
|---|---|---|
| 1 | **Consumer 없음** — terminal 단계(apply/commit/finalize)에 프로덕션 호출자 0 | `apply_pending` 완전 구현+테스트, REST/MCP는 `issue()`만 호출. tombstone이 영영 안 써짐 (PR #530) |
| 2 | **Producer 없음** — 저장소+설정+읽기 API는 있는데 발행하는 코드 0 | `NotificationPrefsRow` 매트릭스와 `needs_you` 기본값까지 정의됐는데, `needs_you`를 emit하는 프로덕션 코드 0줄. docstring: *"v1 stores the PREFERENCES only"* |
| 3 | **입력구 없음** — 워커가 폴링하는 테이블에 행을 넣는 경로 0 | `ScheduleWorker`가 프로덕션 워커 세트에 등록돼 `workspace_schedules`를 폴링. 그런데 리포지토리에 `add()`가 없고 REST·MCP·UI 전무. 행을 만드는 건 테스트뿐 → 엔진은 돌지만 영구히 inert |
| 4 | **클라이언트 전용 상태** — UI 설정이 localStorage에만 있고 서버 로직이 그걸 필요로 함 | timezone 셀렉터가 PWA Settings에 있으나 `localStorage` 전용. quiet-hours 평가는 서버 워커에서 → 영영 못 읽음. (같은 파일의 `language`는 이미 서버로 승격됐는데 `timezone`만 안 따라감) |
| 5 | **SoT 불일치** — 보이는 절반이 진짜 레지스트리 대신 상상한 고정 집합에 맞춰 만들어짐 | 알림 채널의 SoT는 커넥터 바인딩인데 `DEFAULT_CHANNELS = ("in_app","email","slack")` 고정 튜플 → telegram/discord는 플러그인이 있어도 **설정에 표현조차 불가** |

1~3은 "안 만들어짐", 4~5는 "**틀린 모델로** 만들어짐". 후자가 더 위험하다 — 붙일 자리 자체가 안 맞아서 배선하려는 순간 발견된다.

---

## Solution — 진단 레시피

서브시스템마다 **양 끝**을 명시적으로 세라. 프로덕션 호출자를 **센다**. docstring을 믿지 않는다.

### 1. Terminal 동사에 프로덕션 호출자가 있는가

```bash
# apply / commit / finalize / sweep / emit / send / dispatch / resolve / notify
grep -rn --include="*.py" "\.apply_pending(\|\.commit_pending(\|\.sweep(" backend | grep -v test
# 0 → 죽은 코드
```

### 2. 워커가 폴링하는 테이블에 INSERT 경로가 있는가

```bash
# 워커가 claim/poll 하는 테이블마다
grep -rn --include="*.py" "WorkspaceScheduleRow(" backend | grep -v test
grep -rn --include="*.py" "def add\|session.add(WorkspaceScheduleRow" backend/schedule | grep -v test
# 테스트에서만 생성 → 엔진은 돌지만 입력이 영영 없음
```

### 3. 설정 row를 읽는 소비자가 자기 자신의 get/update 말고 있는가

```bash
grep -rn --include="*.py" "NotificationPrefsRow" backend | grep -v test | grep -v "api/v1/notifications\|mcp/tools/notifications"
# 0 → 아무 데도 연결 안 된 스위치
```

### 4. 고정 튜플/enum이 진짜 SoT와 일치하는가

`("in_app","email","slack")` 같은 **하드코딩된 집합**을 보면 즉시 물어라 — *이 목록의 진짜 SoT는 어디인가?* 플러그인 레지스트리? 커넥터 바인딩 테이블? 그렇다면 그 튜플은 **런타임 resolve로 대체**되어야 한다. 안 그러면 SoT에는 있는데 UI에는 표현 불가능한 멤버가 생긴다.

### 5. 클라이언트 설정을 서버가 필요로 하는가

```bash
# PWA에 있는 설정 필드가 백엔드 컬럼으로 존재하는가
grep -rn "timezone" apps/pwa/lib/preferences/     # localStorage?
grep -rn --include="*.py" "timezone.*Mapped" backend    # 서버 컬럼 0개?
```
서버 워커/크론/스케줄러가 그 값으로 판단한다면 **서버 승격 필수**. 같은 파일의 다른 필드가 이미 승격됐다면 그 패턴을 복제하면 된다.

### 6. 스모킹건 — terminal state가 관측되지 않는다

상태머신이 항상 `expired`고 절대 `already_applied`가 안 나온다 → apply가 안 돈다. 로그에 특정 이벤트가 0건 → producer가 없다. **"0이 나온다"는 관측은 producer가 꺼져 있어도 똑같이 나온다** ([[absence-measurement-validity-check]]).

---

## 예방 — Producer 존재 증명 테스트

**이 결함 클래스는 유닛테스트가 100% green이어도 통과한다.** 유닛테스트가 그 메서드를 직접 호출하기 때문이다. 방어는 하나뿐이다:

> **프로덕션 진입점을 실제로 구동해서, 하류 효과가 실제로 생겼는지 확인하는 통합 테스트.**
> `dependency_overrides` 금지. 픽스처 사전 시딩 금지.

```python
# ❌ 이건 이 버그를 못 잡는다 — 메서드를 직접 부르니까
async def test_notifier_sends(notifier, mock_channel):
    await notifier.send(event="needs_you", ...)
    assert mock_channel.sent

# ✅ 이게 잡는다 — 진짜 진입점을 구동하고 하류 행이 생겼는지 본다
async def test_decision_creation_emits_notification(real_app, real_db):
    run = await create_run(real_app)                      # 진짜 REST/MCP 진입점
    await agent_calls_ask_user_question(run)              # 진짜 프로덕션 경로
    rows = await real_db.scalars(select(NotificationEventRow))
    assert len(rows.all()) == 1                           # producer가 프로덕션에 존재하는가
```

리뷰 규율: **새 서브시스템 PR은 양 끝의 프로덕션 호출 지점을 본문에 명시**해야 한다. "producer: X:123, consumer: Y:456". 한쪽을 못 적으면 그 lift는 미완이다.

---

## Key Insights

- **완성돼 보이는 것과 배선된 것은 다르다.** 스키마·UI·워커·테스트가 전부 있어도 서브시스템은 죽어 있을 수 있다.
- **빠지는 절반은 무작위가 아니다.** UI가 없고 유닛테스트가 우회하는 쪽이 빠진다. 그러니 **어디를 볼지 예측할 수 있다.**
- **docstring은 배선의 증거가 아니다.** *"a later phase"*, *"background sweep will handle it"*, *"documented follow-up"* — 전부 미배선의 자백이다.
- **자율 시스템에서는 이게 곧 자율성의 부재다.** 에이전트 파이프라인을 "사람이 방아쇠를 당기는 기계"에서 "스스로 도는 기계"로 만드는 작업은, 대부분 이 안 보이는 절반을 채우는 작업이다.
- 이미 승격/배선된 **형제 필드**를 찾아라 (`language`는 서버로 갔는데 `timezone`은 안 감). 패턴이 있으면 복제하면 되고, 없으면 새로 설계해야 한다.

## Red Flags

- docstring에 *"v1 stores X only"*, *"delivery wiring is a later phase"*, *"LOCAL-ONLY for now, no backend sync"*
- 워커가 런타임에 등록돼 있는데 그 입력 테이블의 리포지토리에 `add()`/`create()`가 없다
- 설정 그리드의 열이 **하드코딩된 튜플**인데, 그 도메인에 실제 레지스트리(플러그인/커넥터/바인딩)가 따로 있다
- 어떤 클래스의 유일한 생성 지점이 `tests/` 안에 있다
- `NotImplementedError` 스텁이 "의도적"이라고 주석돼 있다 (진짜 의도적일 수도 있지만, 대체 경로가 실제로 있는지 확인하라)
- 상태머신의 특정 terminal state가 프로덕션 데이터에 **한 번도** 나타나지 않는다
- 유닛 커버리지는 높은데 그 서브시스템을 **진입점부터 구동하는** 테스트가 없다

## 관련

- [[feedback_queue_apply_step_never_wired]] — 이 스킬의 최초 사례(형태 1)
- [[mock-fixtures-hide-wiring-bugs]] — `dependency_overrides` + 사전 시딩이 프로덕션 글루의 부재를 가린다
- [[absence-measurement-validity-check]] — "0이 관측됨"은 producer가 꺼져 있을 때도 똑같이 나온다
- [[dogfood-automation-bypasses-the-surface-it-tests]] — 검증 경로가 진짜 표면을 우회하는 같은 계열의 함정
