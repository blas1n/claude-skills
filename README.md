# claude-skills

Global [Claude Code](https://docs.anthropic.com/en/docs/claude-code) rules, skills, and commands. Symlinked into `~/.claude/` so they apply across all projects.

## Setup

```bash
ln -s /path/to/claude-skills/rules ~/.claude/rules
ln -s /path/to/claude-skills/skills ~/.claude/skills
ln -s /path/to/claude-skills/commands ~/.claude/commands
```

Claude Code loads both `~/.claude/` (global) and `<project>/.claude/` (project-local) additively. Put shared conventions in global, project-specific ones in local.

## Structure

```
rules/                              # Auto-loaded on every conversation
  python-architecture.md            # Python architecture (uv, pydantic-settings, structlog, async)
  python-security.md                # Security (credentials, logging, input validation)
  python-testing.md                 # Testing (80% coverage, mock patterns, ruff)

skills/                             # Invoked via /skill-name
  code-quality.md                   # ruff + mypy checks
  pre-commit.md                     # Pre-commit checklist
  testing-standards.md              # Testing principles and patterns
  fastapi-guidelines/               # FastAPI DDD patterns (Router → Service → Repository)
  systematic-debugging/             # 4-Phase debugging
  test-driven-development/          # TDD RED-GREEN-REFACTOR
  verification-before-completion/   # Enforce verification before marking done
  dispatching-parallel-agents/      # Parallel agent dispatch
  writing-plans/                    # Execution plan writing
  mermaid/                          # Mermaid diagram generation (23 diagram types)

commands/                           # Invoked via /command-name
  architect.md                      # Architect mode
```

## Credits

Some skills are adapted from open-source projects:

- [obra/superpowers](https://github.com/obra/superpowers) — systematic-debugging, test-driven-development, verification-before-completion, dispatching-parallel-agents, writing-plans
- [chacha95/claude-code-harness](https://github.com/chacha95/claude-code-harness) — mermaid, fastapi-guidelines (generalized)
