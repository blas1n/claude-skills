#!/usr/bin/env bash
# PostToolUse hook: git commit 성공 시 회고 체크 알림
# prompt 훅 대신 command 훅으로 전환 (LLM 호출 없이 패턴 매칭)

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""')
EXIT_CODE=$(echo "$INPUT" | jq -r '.tool_response.exitCode // 0')

# git commit 명령어가 아니면 통과
if [[ "$COMMAND" != git\ commit* ]]; then
  exit 0
fi

# 커밋 실패 시 통과
if [[ "$EXIT_CODE" != "0" ]]; then
  exit 0
fi

# 커밋 성공 → 회고 체크 알림
echo "[retrospective-check] 커밋 완료. 이번 작업에 어려움 신호(방향 전환, 복잡한 원인, 다수 실패 등)가 있었다면 /retrospective를 실행하세요." >&2
exit 2
