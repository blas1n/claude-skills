---
name: a-bound-reported-as-failure-is-retried-past
description: 래핑한 CLI/프로세스에 한도(--max-turns · 토큰 예산 · 시간 상한)를 새로 붙일 때, 그 한도에 닿으면 도구가 **non-zero exit / is_error** 로 끝나는 경우가 많다 — 그리고 래퍼가 "실패 = 재시도"로 배선돼 있으면, 한도가 막은 일을 **새 세션이 처음부터 반복**한다. 한도가 자기를 무력화한다. 붙이기 전에 진짜 CLI 를 한 번 한도에 닿게 돌려 종료 모양을 재고, 한도 도달은 실패가 아니라 "정상 종료 + 표식"으로 매핑하라. 트리거 - `--max-turns`·`--max-tokens`·budget·timeout 플래그 추가, 실행기 래퍼에 세션 내 kill 추가, "실패면 재시도" 루프가 있는 디스패처, stream-json usage 로 세션 중 비용 집계.
---

# A bound reported as failure is retried past

## Problem

에이전트 CLI(claude code 등)를 감싼 실행기에 세션 내 한도를 붙이는 과제. 붙이는 것 자체는
플래그 하나다. 함정은 **한도에 닿았을 때 도구가 끝나는 모양**에 있다.

실측(Claude Code 2.1.286, `--max-turns 2`):
```
result  subtype=error_max_turns  is_error=true
exit code 1
```

이 래퍼의 기존 배선은 이랬다.
- non-zero exit → 터미널 error 청크 → 태스크 `failed`
- 어댑터: `failed` = 일시적 워커 장애 → `retryable=True` → **새 태스크로 재디스패치**

한도를 붙이면, 한도가 막은 라운드를 새 세션이 처음부터 다시 돌리게 된다. 토큰은 두 배로
나가고 한도는 아무것도 막지 못한다. 직접 만든 kill 도 같다. 예산 초과로 프로세스를 죽이고
error 를 내보내면 똑같이 재시도된다.

유닛 테스트로는 이걸 못 잡는다. fake subprocess 는 내가 상상한 종료 모양을 내보낼 뿐이다.

## 같은 프로브에서 함께 나온 것 (stream-json usage)

세션 중 비용을 재려고 assistant 이벤트의 `message.usage` 를 합산하려 했다.
- **content block 마다 같은 `message.id` 로 같은 usage 가 반복된다**(thinking 블록, tool_use 블록 …).
  그대로 합하면 두 배 이상으로 센다. 그러면 예산의 절반에서 세션을 죽인다.
- 그 이벤트의 `output_tokens` 는 스트리밍 **중간값**이다(4, 최종은 233). 입력 측은 정확하다.
- 캐시 쓰기가 1시간 TTL(`ephemeral_1h_input_tokens`)이다. 5분 단가(1.25×)를 가정하면 틀리고, 실제는 2×다.

## Solution

1. **붙이기 전에 진짜 CLI 를 한도에 닿게 한 번 돌린다.** 싼 모델, 빈 디렉터리, 작은 한도로 하면
   비용은 몇 센트다. exit code · 마지막 이벤트 · stderr 를 기록한다.
2. 한도 도달은 **"정상 종료 + 로그 표식"** 으로 매핑한다(`claude_code_max_turns_reached`,
   `..._token_budget_exhausted`). 사용량은 터미널 청크에 그대로 싣는다. 그러면 상위의 회계·상한
   검사가 평소처럼 판단한다(예: run_token_cap Decision).
3. 판정 근거는 exit code 가 아니라 **subtype** 으로 좁힌다(`rc != 0 and subtype == "error_max_turns"`).
   다른 non-zero 는 여전히 실패다.
4. 세션 중 집계는 `message.id` 로 키잉하고 필드별 max 를 취한다. 합산하지 않는다.
5. 테스트 픽스처는 **실측한 이벤트를 그대로 복사**해서 쓴다. 상상한 모양으로 만들지 않는다.
   그리고 "한도 도달 → error 없음" 테스트를 둔다. 전선 절단(정규화 줄 제거)으로 그 테스트가
   빨개지는지 확인한다.

## Checklist

- [ ] 한도 도달 시 exit code / 최종 이벤트를 실측했는가
- [ ] 상위 경로에 "실패 → 재시도"가 있는가? 있다면 한도 도달이 그 경로를 타지 않는가
- [ ] 직접 만든 kill(예산 초과)도 실패가 아닌 종료로 나가는가
- [ ] usage 누적이 블록 반복을 중복 제거하는가
- [ ] 래퍼가 원격 호스트에 배포되는가(워커는 autodeploy 가 아닐 수 있다 — 재시작 확인)

## Related

- [[external-cli-wrapper-contract-drift]] — mock 이 외부 계약을 검증하지 못하는 일반형
- [[agentic-cli-as-llm-transport]]
- [[a-check-that-cannot-flip-is-not-measuring-anything]]
