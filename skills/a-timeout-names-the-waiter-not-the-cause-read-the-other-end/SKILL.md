---
name: a-timeout-names-the-waiter-not-the-cause-read-the-other-end
description: "타임아웃은 기다린 쪽의 경험이지 사건의 원인이 아니다. 보고 홉(worker→backend, client→API, job→queue)이 보내는 쪽에서 응답을 안 보고 받는 쪽에서 거절을 200 으로 돌려주면, 실패한 쓰기가 성공 로그로 세탁된다 — 그리고 한쪽 끝만 읽어 만든 진단표에는 진실이 들어갈 칸이 아예 없다. 두 끝을 같은 타임스탬프로 나란히 읽어라: 모순 자체가 진단이다. 트리거 - '왜 자꾸 타임아웃이지', 재현 안 되는 간헐 행(hang), 같은 증상을 두 번 이상 오진한 이력, 종결되지 않고 쌓이는 in-flight 행."
version: 1.0.0
task_types: [debugging, review, ops]
triggers:
  - pattern: "await/poll 이 timeout 을 올렸는데 원인이 '상대가 응답 안 함' 으로만 적힐 때"
  - pattern: "in-flight/dispatched/pending 상태 행이 종결 없이 쌓여 있을 때"
  - pattern: "같은 증상으로 계측을 추가했는데 그 계측이 침묵한 이력이 있을 때"
  - pattern: "보내는 쪽 로그는 success, 받는 쪽 상태는 미완료일 때"
category: trap
---

# 타임아웃은 기다린 쪽의 경험이다 — 반대쪽 끝을 읽어라

## Problem

- **증상**: 오케스트레이터가 `TimeoutError` 를 올린다. 작업은 "상대가 응답하지 않음"으로
  기록되고, 상태 행은 `dispatched` / `in_flight` 로 영원히 남는다. 드물게(월 몇 건) 터지고
  재현이 안 된다.
- **근본 원인**: 상대는 **5초 만에 끝냈다.** 결과 보고 POST 가 거절당했고,
  - 보내는 쪽은 `raise_for_status()` 없이 응답을 버렸으며 바로 다음 줄에 `success=True` 를 찍었고,
  - 받는 쪽은 보안상(프로빙 방지) **거절도 200** 으로 돌려줬다.
  실패한 쓰기가 양쪽 모두에서 성공으로 보인다.
- **흔한 오해**: "타임아웃 = 상대가 느리거나 죽었다". 그래서 계측을 **기다리는 쪽에** 더
  붙이고, 기다리는 쪽이 관측한 것들로 진단표를 만든다. 그 표는 아무리 정교해져도
  **반대쪽에서만 보이는 칸**을 가질 수 없다.

실제 사례에서 `TaskTimeout` 독스트링은 네 칸짜리 표를 갖고 있었다:

```
* polls 가 만점 + last_status 가 'dispatched' → 워커가 보고를 안 했다     ← 틀렸다
* polls 가 만점 + last_status 가 None        → 행이 안 보인다
* polls 가 바닥                              → 대기 루프가 굶었다
* last_status 가 terminal                    → 읽기가 다 놓쳤다
```

두 번(#821·#828) 조사했고 두 번 다 첫 칸으로 읽었다. 첫 칸의 문장이 **"워커가 보고를
안 했다"** 인데, 진실은 **"워커는 보고했고 그 보고가 안 착지했다"** 였다.
두 문장은 기다리는 쪽에서 **완전히 동일하게 보인다.**

## Solution

1. **두 끝을 같은 타임스탬프로 나란히 놓아라.** 한쪽만으로는 어느 문장도 모순이 아니다.
   나란히 놓는 순간 증명이 된다.

   | 시각 | 보내는 쪽 로그 | 받는 쪽 DB 행 |
   |---|---|---|
   | 16:33:15 | `task_received` | `status='dispatched'` |
   | 16:33:20 | `task_completed success=True` | `status='dispatched'` ← **모순** |
   | 16:36:15 | — | 여전히 `dispatched`, 대기자는 180s 타임아웃 |

2. **보고 홉의 응답을 검사하는지 세라.** 같은 파일의 *다른* 호출들과 비교하는 게 가장 빠르다 —
   보통 `register` / `poll` 은 `raise_for_status()` 를 부르고 **결과 보고만 안 부른다.**

   ```python
   async def _post_result(client, headers, *, payload) -> None:
       res = await client.post(_RESULT_PATH, headers=headers, json=payload)
       if res.is_success:
           return
       logger.error("result_post_rejected", task_id=payload.get("task_id"),
                    status_code=res.status_code, body=res.text[:500])
       res.raise_for_status()      # 시끄러운 게 목적이다
   ```
   호출부가 이미 `except Exception` 으로 루프를 지키고 있는지 확인하면 raise 가 안전하다.

3. **상태를 종결하는 코드가 있는지 `.status = ` 로 전수 조사하라.** "reaper 가 있겠지"를
   믿지 마라. 실제로 백엔드 전체에 쓰기가 **정확히 둘**이었다(진입 · 정상 종료). 즉
   **타임아웃 경로에는 종결이 없었다** — 대기자는 포기하는데 행은 영원히 in-flight 다.

4. 종결을 넣을 땐 **조건부 UPDATE** 로. 레이스 창에서 진짜 결과가 착지했을 수 있다.
   ```sql
   UPDATE tasks SET status='failed', error_message=:why
    WHERE id=:id AND status='dispatched'
   ```
   `rowcount` 가 "내가 닫았다"의 유일한 증거다.

5. **받는 쪽의 200-on-refusal 은 함부로 깨지 마라.** 그게 의도(프로빙 방지)일 수 있고,
   보통 독스트링이 변호한다. 대신 **거절을 서버 쪽 로그로** 남기고, 보내는 쪽은
   전송/서버 오류(401·422·5xx)만 잡게 하라. 그러면 모든 실패가 **최소한 한쪽에서는** 이름을 갖는다.

## Key Insights

- **타임아웃은 원인이 아니라 관측이다.** `deriver_error: TimeoutError` 는 "LLM 이 느렸다"로
  읽히지만 실제로는 "내가 기다리다 지쳤다"만 말한다. 원인은 **반대쪽에** 있다.
- **한쪽 끝에서 만든 진단표는 계속 정교해지면서 계속 틀린다.** 표의 칸을 늘리기 전에
  **표가 읽고 있는 축이 하나뿐인지** 물어라. 두 번 오진한 이력이 있으면 거의 확실히 그렇다.
- **실패한 쓰기는 실패한 읽기보다 조용하다.** 읽기 실패를 `[]` 로 접는 결함은 값이 비어서
  티라도 나지만, 쓰기 실패는 **보낸 쪽에 성공 로그를 남기므로** 증거가 적극적으로 반대를
  가리킨다. (자매편: `a-failed-read-degraded-to-empty-becomes-a-measurement`)
- **드묾은 무해함이 아니다.** 4개월간 147건이면 "월 1~2건"이지만, 각각은 런 하나가
  풀 타임아웃을 태우고 틀린 원인을 기록한 사건이다. 그리고 그 토큰은 **어디에도 계상되지 않는다** —
  과금/쿼터를 설계 중이라면 이건 조용한 미계상 채널이다.

## Red Flags

- 기다리는 쪽 예외 메시지에 원인이 "상대가 응답 안 함"으로만 적혀 있다.
- 같은 증상으로 **전에도 계측을 추가했는데 그 계측이 침묵했다**는 기록이 있다.
  (침묵은 "문제 없음"이 아니라 **가설이 틀렸다**는 뜻이다.)
- 한 파일 안에서 어떤 호출은 `raise_for_status()` 를 부르고 어떤 호출은 안 부른다.
- `pending` / `dispatched` / `in_flight` 상태 행이 **오래된 것부터 쌓여** 있다.
- 상태 전이 코드를 전수 조사하면 **진입은 있는데 타임아웃 종결이 없다.**
- 받는 쪽 라우트가 거절 경로에서도 `200` 을 돌려준다 (보안 의도일 수 있음 — 깨지 말고 로그를 확인).
