---
name: guard-must-borrow-the-systems-own-lease
description: "죽었나 살았나"를 스스로 고른 신선도 창(3분 등)으로 판정하는 가드·워치독·리퍼·헬스체크는, 보호 대상 시스템이 자기 계약서에 적어둔 lease(예: 한 턴 최대 1시간)와 어긋나면 **가장 값진 작업 구간에서 정확히 오판**한다. 트리거 - `updated_at > now() - interval 'N minutes'`, "in flight 면 배포 연기", stale-claim 리퍼, liveness/readiness probe, 배포 직전 드레인 가드, "재시작했더니 작업이 날아갔다".
---

# 가드는 생존 판정을 스스로 발명하지 말고 시스템에서 빌려와야 한다

## Problem

배포·재시작·정리 직전에 "지금 뭔가 돌고 있나?"를 묻는 가드는 대개 이렇게 짠다:

```bash
running=$(psql -tAc "select count(*) from execution_runs
                     where status in ('running','open')
                       and updated_at > now() - interval '3 minutes'")
[ "$running" -gt 0 ] && defer_deploy
```

- **증상**: 가드가 있는데도 살아있는 작업이 재시작에 깔려 죽는다. 로그를 보면
  **가드가 몇 분 전까지 "in flight"라고 기록해놓고** 바로 다음 주기에 통과시켰다.
- **근본 원인**: 3분은 **가드 저자가 고른 숫자**다. 보호 대상 시스템은
  자기 소스에 전혀 다른 계약을 적어두고 있다:

  ```python
  @property
  def _stale_claim_lease_s(self) -> float:
      """... a SINGLE turn can legitimately run up to executor_task_timeout_s
      (1 h) and the loop refreshes claimed_at only at each turn BOUNDARY, so a
      single long turn running a full test suite goes the WHOLE turn without
      refreshing its claim."""
      return 2.0 * self._settings.executor_task_timeout_s   # 2시간
  ```

  **3분 vs 1시간 — 20배.** 게다가 침묵이 가장 긴 구간은 하필 *전체 테스트를 도는
  검증 단계*, 즉 그 작업에서 가장 값진 부분이다. 가드는 구조적으로 그때 오판한다.
- **흔한 오해**: "신선도 창을 늘리면 좀비 행이 배포를 영원히 막는다."
  → 아니다. 시스템의 lease 자체가 만료 기준이므로 **쿼리가 스스로 만료된다.**
  lease 를 넘긴 행은 정의상 리퍼의 것이지 가드의 것이 아니다.

## Solution

1. **보호 대상의 소스에서 생존 정의를 찾아라.** 대개 리퍼/스위퍼 옆에 주석까지
   붙어 있다 (`_stale_claim_lease_s`, `visibility_timeout`, `lock_ttl`,
   `heartbeat_interval * N`). 같은 레포의 다른 감시 스크립트도 확인 — 이번 사례에서
   `watchdog.sh` 는 이미 2시간을 쓰고 있었고 배포 가드의 3분만 예외였다.
2. **"최근에 뭔가 썼다"가 아니라 "권리를 쥐고 있다"로 판정하라.**
   `updated_at`(활동 흔적)은 긴 단일 작업 동안 멈춘다. `claimed_at`/lock/lease 는
   *소유권*이고 갱신 주기가 계약에 명시돼 있다.
3. **lease 를 하드코딩하지 말고 같은 설정에서 파생하라.**
   ```bash
   turn_cap_s=$(docker exec <backend> printenv APP_TASK_TIMEOUT_S || echo 3600)
   lease_s=$(( ${turn_cap_s%.*} * 2 ))
   ```
4. **lease 안에서도 확실히 죽었다고 알 수 있는 경우는 즉시 배제하라.**
   루프가 컨테이너 안에 산다면, **컨테이너 기동 시각보다 오래된 claim 은 고아**다.
   이게 없으면 죽은 작업 하나가 lease 내내(2시간) 배포를 막는다.
   ```sql
   and claimed_at > '<container StartedAt ISO>'::timestamptz
   ```
5. **판정식을 한 곳으로 빼서 실 DB 픽스처로 테스트하라.** bash 안에 인라인된
   SQL 은 테스트가 안 된다. 함수로 추출하면 8케이스가 30초에 돈다.

## 반대 방향 오류도 같이 나온다

같은 쿼리가 **보호하지 말아야 할 것까지 보호**하고 있었다:
`status in ('running','open')` 의 `open` 은 **아직 아무도 집지 않은 큐 대기 행**이다.
중단시킬 루프가 없으므로 보호할 이유가 없는데, 배포는 막았다.

> 생존 판정 버그는 대개 **양방향**이다. 테스트 케이스를 "살아있는데 방치"와
> "죽었는데/안 도는데 보호" 둘 다 써라.

## Key Insights

- **가드 로그가 스스로를 고발한다.** `14:48:57 in flight — deferring` 다음에
  `14:51:01 rebuilding` 이면, 가드는 2분 전 살아있다고 본 것을 죽인 것이다.
  사고 조사에서 **가드 자신의 로그를 시계열로 먼저 붙여라.**
- **침묵 길이는 추측하지 말고 그 시스템에서 재라.** 이번엔 대상 작업이 선언한
  `uv run pytest -ra` 가 **353초**였고, 활동 간격 최댓값은 **8분 39초**였다.
  실 런으로 재보니 살아있는 동안 최대 **393초** 침묵 — 3분 창의 2.2배.
- **"좀비가 배포를 영원히 막는다"는 걱정이 짧은 창을 정당화하지 못한다.**
  lease 기반 쿼리는 자동 만료되고, 고아 감지가 그 안쪽까지 덮는다.
- 다음에 이 냄새를 맡거든: *가드가 쓰는 임계값이 코드 어딘가에 이미 다른 이름으로
  적혀 있지 않은지* 를 가장 먼저 grep 하라.
