---
name: external-cli-wrapper-contract-drift
description: 외부 CLI/API(claude code, codex, opencode 등)를 subprocess/HTTP로 감싼 wrapper는 그 CLI가 버전업하면 인자·요청바디·출력파싱이 silent하게 drift한다. 경계를 mock한 테스트는 아무 형식이나 받아주므로 wrapper가 죽어도 green. 실제 CLI의 --help / OpenAPI /doc / published SDK 타입으로 계약을 검증하라.
---

# External CLI/API Wrapper Contract Drift

## Problem

빠르게 버전업하는 외부 도구(Claude Code, Codex, opencode, gh, terraform CLI 등)를
subprocess 호출이나 HTTP 클라이언트로 감싼 wrapper를 만든다. 시간이 지나면 그 외부
도구의 인자·하위명령·요청 바디·출력 이벤트 스키마가 바뀌는데, wrapper는 옛 계약 그대로
멈춰 있다.

- **증상**: 단위 테스트 100% green인데 실제로는 wrapper가 동작 안 함.
  - codex executor: `message_delta` 이벤트를 파싱했는데 codex 0.130은 `item.completed`/
    `agent_message`만 emit → 출력이 항상 빈 문자열.
  - codex: `--config experimental_instructions_file=` 가 `model_instructions_file`로
    rename됨 → 구키는 codex가 **읽지도 않아** system prompt가 조용히 유실.
  - opencode: 메시지 바디를 `{role, content}`로 POST하는데 현재 계약은 `{parts:[...]}`
    → `parts` 필수라 거부/무시.
- **근본 원인**: 테스트가 subprocess(`create_subprocess_exec`)나 `httpx.AsyncClient`를
  mock한다. mock은 **어떤 인자/바디를 줘도 받아준다.** 즉 mock은 *내 코드*를 검증할 뿐
  *외부 도구의 계약*은 전혀 검증하지 않는다. 외부 도구가 버전업해도 테스트는 빨갛게
  변하지 않는다 — wrapper만 조용히 썩는다.
- **흔한 오해**: "테스트 green이고 cmd_args / 요청바디 assert도 있으니 맞다." → 그
  assert는 *내가 보낸 것*과 *내가 기대한 것*을 비교할 뿐, 둘 다 틀려도 통과한다.
  outbound-shape mock-drift는 inbound response-shape drift([[e2e-mock-shape-drift]])의
  거울상이다.

## Solution

외부 CLI/API를 감쌀 때 — 또는 기존 wrapper를 의심할 때:

1. **published 타입 계약을 SoT로 삼아라.** 추측·옛 메모리·dev 브랜치 추정 금지.
   - HTTP API: 서버를 실제로 띄우고 `GET /doc`(OpenAPI 스펙)을 받아라. 또는 published
     SDK의 생성 타입(`@scope/sdk@<버전>/dist/gen/types.gen.d.ts`)을 확인.
   - CLI: 실제 설치본의 `<cmd> --help` / `<cmd> <subcmd> --help`.
2. **실제로 한 번 돌려라(real smoke).** 인증이 필요하면 우회 경로를 찾아라.
   - codex: `--oss --local-provider ollama -m <local-model>` 으로 OpenAI 인증 없이 실행.
   - 출력 이벤트 스키마는 추측 말고 실제 한 줄을 캡처해 눈으로 확인.
3. **wrapper가 만드는 *정확한* 인자/바디 조합**으로 검증하라. 일부만 맞으면 통합에서 깨진다.
4. deprecated 신호를 무시하지 마라. `experimental_` prefix, `--help`에 안 보이는 플래그,
   실행 시 `warning: X is deprecated` → 곧 제거된다.
5. 테스트에 **real-CLI smoke test 한 개**를 추가하거나, 최소한 wrapper 작성 시 계약을
   캡처한 출처(버전 번호 + 날짜)를 주석/PR에 박아라. mock 단위 테스트는 그대로 두되
   그것만 믿지 마라.

```python
# 검증 예 — wrapper가 만드는 그 플래그 그대로, 실제 CLI에 (auth 우회로) 실행
# $ echo "prompt" | codex exec --json --sandbox workspace-write \
#     --config model_instructions_file=/tmp/sys.md --oss --local-provider ollama -m qwen3-coder:30b
# → {"type":"item.completed","item":{"type":"agent_message","text":"..."}}  ← 실제 스키마 확인
```

## Key Insights

- **경계를 mock하면 그 경계 너머의 계약은 검증 불가능하다.** subprocess args assert,
  HTTP body assert는 "내가 의도대로 보냈나"만 본다. "그게 외부 도구가 받는 형식인가"는
  오직 실제 도구(또는 그 published 스펙)만 답한다.
- **wrapping한 도구가 빠르게 움직이면 wrapper는 부패 자산이다.** 한 번 "검증된" 계약
  주석("verified against opencode upstream at PR #26 time")은 6개월 뒤 거짓이 된다.
  계약 검증은 wrapper를 만질 때마다 다시 한다.
- **input(인자/바디)뿐 아니라 output(이벤트/응답 파싱)도 같이 drift한다.** 모델 지정
  같은 작은 기능을 추가하다가 wrapper 전체가 죽어 있던 걸 발견하는 경우가 흔하다 —
  작은 기능이라도 그 경로 전체의 현재 계약을 확인하라.
- 인증 때문에 real e2e가 막히면 포기하지 말고 우회로(로컬 OSS provider, 스펙 엔드포인트
  `/doc`, dry-run 플래그)를 찾아라. 계약 검증은 full e2e 없이도 대부분 가능하다.

## Red Flags

- subprocess(`asyncio.create_subprocess_exec`) 또는 `httpx`를 mock하는 executor/wrapper
  테스트가 100% green인데 실제 동작을 본 사람이 없다.
- 코드에 외부 CLI 플래그/요청바디가 하드코딩돼 있고, 그 옆 주석에 "verified at <옛 시점>".
- `experimental_` 로 시작하는 설정 키, 또는 외부 도구가 빠르게 릴리스되는데(주간 단위)
  wrapper는 몇 달째 그대로.
- 외부 CLI 실행 시 `warning: ... deprecated` 가 떠도 무시되고 있다.
- "model 지정만 추가" 같은 작은 작업인데 그 경로(요청바디/출력파싱)가 애초에 옛 형식.
