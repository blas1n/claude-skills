#!/usr/bin/env bash
# 폴링 기반 자동 커밋: claude-skills의 skills/, rules/ 변경을 감지해 커밋
# macOS LaunchAgent에서 주기적으로 호출됨

SKILLS_DIR="$HOME/.claude/claude-skills"
cd "$SKILLS_DIR" || exit 0

# skills/, rules/ 변경 확인
CHANGED=$(git status --porcelain -- skills/ rules/ 2>/dev/null)
[ -z "$CHANGED" ] && exit 0

# frontmatter에서 스킬 이름 추출
NAMES=""
while IFS= read -r line; do
  FILE=$(echo "$line" | awk '{print $2}')
  if [[ "$FILE" == *.md ]]; then
    NAME=$(grep '^name:' "$SKILLS_DIR/$FILE" 2>/dev/null | head -1 | sed 's/^name: *//')
    [ -n "$NAME" ] && NAMES="${NAMES}${NAME}, "
  fi
done <<< "$CHANGED"
NAMES="${NAMES%, }"

# 커밋 메시지 구성
if [ -n "$NAMES" ]; then
  MSG="feat(skills): retrospective assets - ${NAMES}"
else
  MSG="feat(skills): retrospective assets"
fi

git add skills/ rules/
git commit -m "$MSG"
