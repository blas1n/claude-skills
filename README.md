# claude-skills

Claude Code의 글로벌 rules, skills, commands 모음. `~/.claude/`에 symlink하여 모든 프로젝트에서 공통으로 사용한다.

## 설치

```bash
ln -s ~/Works/claude-skills/main/rules ~/.claude/rules
ln -s ~/Works/claude-skills/main/skills ~/.claude/skills
ln -s ~/Works/claude-skills/main/commands ~/.claude/commands
```

Claude Code는 `~/.claude/` (글로벌) + `<project>/.claude/` (프로젝트) 양쪽을 로드한다. 글로벌에는 공통 규칙, 프로젝트에는 고유 규칙만 둔다.

## 구조

```
rules/                              # 자동 로드되는 규칙
  python-architecture.md            # Python 아키텍처 (uv, pydantic-settings, structlog, async)
  python-security.md                # 보안 (credentials, logging, input validation)
  python-testing.md                 # 테스트 (80% coverage, mock, ruff)

skills/                             # /skill-name 으로 호출하는 스킬
  code-quality.md                   # ruff + mypy 체크
  pre-commit.md                     # 커밋 전 체크리스트
  testing-standards.md              # 테스트 원칙/패턴
  fastapi-guidelines/               # FastAPI DDD 패턴
  systematic-debugging/             # 4-Phase 디버깅 (obra/superpowers)
  test-driven-development/          # TDD RED-GREEN-REFACTOR (obra/superpowers)
  verification-before-completion/   # 완료 전 검증 강제 (obra/superpowers)
  dispatching-parallel-agents/      # 병렬 에이전트 디스패치 (obra/superpowers)
  writing-plans/                    # 실행 계획 작성 (obra/superpowers)
  mermaid/                          # Mermaid 다이어그램 생성 (chacha95/claude-code-harness)

commands/                           # /command-name 으로 호출하는 명령
  architect.md                      # 아키텍트 모드
```

## Credits

일부 skills는 외부 오픈소스에서 가져왔다:

- [obra/superpowers](https://github.com/obra/superpowers) — systematic-debugging, test-driven-development, verification-before-completion, dispatching-parallel-agents, writing-plans
- [chacha95/claude-code-harness](https://github.com/chacha95/claude-code-harness) — mermaid, fastapi-guidelines (일반화)
