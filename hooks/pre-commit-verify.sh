#!/usr/bin/env bash
# PreToolUse hook: git commit 시 테스트 자동 실행 및 Playwright 감지
# Claude Code settings.json의 PreToolUse → Bash 매처에서 호출됨

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""')
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

# git commit 명령어만 인터셉트
if [[ "$COMMAND" != git\ commit* ]]; then
  exit 0
fi

cd "$CWD" 2>/dev/null || exit 0
FAILED=0

# Python 프로젝트: uv + pytest
if [ -f "pyproject.toml" ] && command -v uv &>/dev/null; then
  echo "[pre-commit] Running pytest..."
  if ! uv run pytest tests/ --tb=short -q 2>&1; then
    echo "BLOCKED: Unit tests failed. Fix before committing." >&2
    FAILED=1
  fi
# Node 프로젝트: npm test
elif [ -f "package.json" ] && command -v npm &>/dev/null; then
  echo "[pre-commit] Running npm test..."
  if ! npm test --if-present 2>&1; then
    echo "BLOCKED: Tests failed. Fix before committing." >&2
    FAILED=1
  fi
fi

# Playwright 실행 (웹 프로젝트 판단)
IS_WEB=0
if [ -f "playwright.config.ts" ] || [ -f "playwright.config.js" ]; then
  IS_WEB=1
elif [ -f "package.json" ] && grep -qE '"(react|vue|next|nuxt|svelte|angular)"' package.json 2>/dev/null; then
  IS_WEB=1
fi

if [ "$IS_WEB" -eq 1 ] && [ "$FAILED" -eq 0 ]; then
  if command -v npx &>/dev/null && ([ -f "playwright.config.ts" ] || [ -f "playwright.config.js" ]); then
    echo "[pre-commit] Web project detected, running Playwright e2e tests..."
    if ! npx playwright test 2>&1; then
      echo "BLOCKED: Playwright e2e tests failed." >&2
      FAILED=1
    fi
  elif [ "$IS_WEB" -eq 1 ]; then
    echo "[pre-commit] Web project detected but no playwright.config found. Consider setting up Playwright e2e tests." >&2
  fi
fi

[ "$FAILED" -eq 1 ] && exit 2
exit 0
