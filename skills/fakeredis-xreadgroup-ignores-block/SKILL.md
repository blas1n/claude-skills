---
name: fakeredis-xreadgroup-ignores-block
description: fakeredis(aioredis) 의 XREADGROUP 은 `block=` 을 무시하고 즉시 빈 결과를 돌려준다 — 실제로 suspend 하지도 않아서 `while not stop: await xreadgroup(..., block=1000)` 소비 루프가 이벤트 루프를 굶겨 테스트가 영원히 멈춘다. 그리고 컨슈머 그룹을 `id="$"` 로 만들면 그룹 생성 전에 XADD 된 메시지를 건너뛴다. 트리거: fakeredis 로 스트림 소비자 테스트가 hang, pytest 가 첫 테스트에서 멈춤, 요청/응답이 타임아웃.
---

# fakeredis 의 XREADGROUP 은 block 하지 않는다

## Problem

Redis 스트림 요청/응답(소비자 루프 + 호출자 BLPOP)을 fakeredis 로 테스트하면 테스트가 멈춘다.

```python
while not stop.is_set():
    batches = await redis.xreadgroup(GROUP, consumer, {stream: ">"}, count=16, block=1000)
    for _s, entries in batches or []:
        ...
```

- 실제 Redis: `block=1000` 동안 대기 → 루프가 다른 태스크에 양보한다.
- fakeredis: 즉시 `[]` 반환, **await 가 suspend 하지 않음** → 루프가 CPU 를 독점, 호출자 태스크가
  돌지 못한다. `BLPOP timeout=` 은 제대로 양보한다(측정함) — XREADGROUP block 만 문제.

두 번째 함정: 소비자 태스크를 만들고(`create_task`) 곧바로 호출자가 XADD 하면, 소비자가
`xgroup_create(..., id="$")` 를 실행하기 **전**에 메시지가 들어가 그룹이 그걸 건너뛴다 →
응답 없음 → 타임아웃. 프로덕션에서도 "그 머신이 처음 서빙을 시작하기 전에 온 요청" 이 같은 이유로 버려진다.

## Solution

```python
if not batches:
    # BLOCK 이 대기다; 이건 조기 반환한 읽기가 스핀하지 않게 할 뿐.
    await asyncio.sleep(0.05)
    continue
```

- 실제 Redis 가 일찍 반환하는 경우(연결 문제 등)에도 스핀을 막으므로 프로덕션 코드로 정당하다.
- 그룹은 `id="0"` 으로 만들고, 오래된 메시지는 **요청에 실은 deadline** 으로 버린다
  (`if call["deadline"] < time.time(): continue`). at-most-once(읽자마자 XACK)와 함께 쓴다.

## 진단 팁

- 멈춘 테스트는 `perl -e 'alarm 60; exec @ARGV' uv run pytest ...` 로 감싸 단일 테스트부터 (macOS 엔 `timeout` 없음).
- 짧은 스크립트로 fakeredis 동작을 직접 측정: 동시에 0.2s ticker 태스크를 돌리며 `xreadgroup(block=500)` 이
  얼마 걸리는지, ticker 가 찍히는지 본다.
