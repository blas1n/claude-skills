---
name: waiting-on-a-human-is-not-an-outage
description: 사람의 결정을 기다리는 작업을 "실행 중" 상태로 파킹해두면, 시간 기반 stall/wedge 모니터가 그걸 장애로 읽어 답을 기다리는 그 사람에게 장애 알람을 보낸다. 트리거 - 승인 대기·질문 대기 상태 설계, "N시간+ running 이면 wedge" 류의 모니터, 사용자가 "자꾸 이상 감지 알림이 온다"고 할 때, 대기 큐가 있는 시스템의 알림 튜닝.
---

# 기다림은 고장이 아니다

## Problem

BSVibe 2026-08-12. 머지 충돌이 자동 재시도를 소진하면 형님에게 Decision 을 올리고
런을 **`RUNNING` 에 파킹**한다. 의도적이다 — `drive_once` 가 `OPEN` 만 집으므로
`RUNNING` 이 "지금은 네 것 아니다"를 뜻하는 관례다.

ops 워치독은 따로 있었다:

```bash
wedged=$(psql "select count(*) from execution_runs
               where status in ('running','open')
                 and updated_at < now() - interval '2 hours'")
[ "$wedged" -gt 0 ] && add "⚙️ run ${wedged}건이 2h+ running/open에 끼임 (wedge 의심)"
```

⇒ **형님이 2시간 안에 답을 안 하면, 그 기다림이 `🚨 프로덕션 이상 감지` 가 되어
30분마다 폰을 쳤다.** 답을 기다리는 사람에게 제품이 고장났다고 알리는 구조다.

증상이 특히 나쁜 이유: 알람이 오면 사람은 **답하는 대신 장애를 조사한다.** 그리고
조사하는 동안 시간이 더 흘러 알람이 또 온다.

## Root shape

두 서브시스템이 같은 상태 값에 **다른 의미**를 걸었다:

| | 의미 |
|---|---|
| 실행 루프 | `RUNNING` = 이 런은 루프가 집을 대상이 아니다 (파킹 포함) |
| 모니터 | `RUNNING` 오래 = 아무도 진행시키지 않는다 = 고장 |

둘 다 자기 맥락에선 맞다. 어긋난 건 **"오래 걸림"의 원인을 구분하지 않은 것**이다.

## Solution

시스템이 **이미 알고 있는 사실**로 의도된 대기를 판별한다. 대기 중인 Decision 행이
바로 그 기록이다:

```sql
select count(*) from execution_runs r
 where r.status in ('running','open')
   and r.updated_at < now() - interval '${WEDGE_S} seconds'
   and not exists (select 1 from execution_decisions d
                    where d.run_id = r.id and d.status = 'pending')
```

원칙:

- **모니터 쪽을 고친다.** 파킹 관례 자체는 멀쩡하다(파킹된 런은 정말 실행 중인
  워크플로다). 틀린 건 *"오래 = 고장"* 이라는 추론이다. 상태기계를 쪼개는 리팩터는
  drive loop·UI·resume 경로까지 번지므로 비용이 훨씬 크다.
- **판별자는 서버의 기록이어야 한다.** 시간·휴리스틱이 아니라 "왜 기다리는지"를
  적어둔 행. 그게 없으면 애초에 파킹이 불투명하다는 뜻이다.
- **진짜 wedge 탐지는 살려둔다.** 대기 Decision 이 **없는** 오래된 런은 여전히 알람.
  양성/음성 대조를 실 데이터에 롤백 트랜잭션으로 걸어 확인할 것.

## Detection

- 사용자가 "자꾸 이상 알림이 온다"고 하는데 제품은 멀쩡하다
- 알람 문구가 시간 임계값만 근거로 한다("N시간+", "stale", "wedge 의심")
- 승인/질문 큐가 있는 시스템에서, 큐가 길수록 알람이 늘어난다
- 알람 수신자와 대기의 원인(결정권자)이 **같은 사람**이다
