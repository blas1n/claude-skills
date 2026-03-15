#!/usr/bin/env bash
# PostToolUse hook: 테스트 실패 시 체계적 디버깅 알림
# prompt 훅 대신 command 훅으로 전환 (LLM 호출 없이 패턴 매칭)

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""')
EXIT_CODE=$(echo "$INPUT" | jq -r '.tool_response.exitCode // 0')

# 테스트 명령어인지 확인
IS_TEST=0
case "$COMMAND" in
  *pytest*|*"npm test"*|*"npm run test"*|*jest*|*vitest*|*"go test"*|*"cargo test"*|*unittest*)
    IS_TEST=1
    ;;
esac

if [[ "$IS_TEST" -eq 0 ]]; then
  exit 0
fi

# 테스트 성공 시 통과
if [[ "$EXIT_CODE" == "0" ]]; then
  exit 0
fi

# 테스트 실패 → 디버깅 알림
echo "[systematic-debugging] 테스트 실패 감지. 근본 원인부터 조사하세요 — Phase 1: 에러 메시지 읽기, 재현, 최근 변경 확인. 추측으로 수정하지 마세요." >&2
exit 2
