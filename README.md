# claude-skills

Global [Claude Code](https://docs.anthropic.com/en/docs/claude-code) rules, skills, and commands. Symlinked into `~/.claude/` so they apply across all projects.

## Setup

```bash
ln -s /path/to/claude-skills/rules ~/.claude/rules
ln -s /path/to/claude-skills/skills ~/.claude/skills
ln -s /path/to/claude-skills/commands ~/.claude/commands
ln -s /path/to/claude-skills/hooks ~/.claude/hooks
ln -s /path/to/claude-skills/settings.json ~/.claude/settings.json
```

Claude Code loads both `~/.claude/` (global) and `<project>/.claude/` (project-local) additively.

## Structure

```
rules/                              # Auto-loaded on every conversation
  python-architecture.md            # Python architecture (uv, pydantic-settings, structlog, async)
  python-security.md                # Security (credentials, logging, input validation)
  python-testing.md                 # Testing (80% coverage, mock patterns, ruff)
  tdd-enforcement.md                # Mandatory TDD for all implementation work
  retrospective-discipline.md       # Auto-trigger retrospective on difficult tasks

commands/                           # Invoked via /command-name
  architect.md                      # Architect mode

hooks/                              # Shell hooks for tool events
  pre-commit-verify.sh              # Pre-commit verification
  post-commit-retrospective.sh      # Post-commit retrospective trigger
  post-test-debug-reminder.sh       # Debug reminder after test failures
  session-start-stitch.sh           # Session start Stitch setup
  stop-notify.sh                    # Stop notification

skills/                             # Invoked via /skill-name (53 skills)
  _registry.json                    # Auto-generated index
  SKILL-FORMAT.md                   # YAML frontmatter schema standard
```

## Skills by Category

### Think & Plan (gstack + OMC)
| Skill | Source | Description |
|-------|--------|-------------|
| `/deep-interview` | OMC | Socratic questioning with ambiguity scoring |
| `/office-hours` | gstack | Product ideation with forcing questions |
| `/writing-plans` | superpowers | Multi-step implementation planning |
| `/plan-eng-review` | gstack | Architecture/test matrix review |
| `/plan-design-review` | gstack | Design dimension 0-10 scoring |
| `/autoplan` | gstack | Automated multi-review pipeline |

### Build & Code
| Skill | Source | Description |
|-------|--------|-------------|
| `/coding-general` | self | Generic coding skill |
| `/feature-workflow` | self | TDD+E2E full lifecycle |
| `/test-driven-development` | superpowers | Red-Green-Refactor TDD |
| `/fastapi-guidelines` | self | FastAPI DDD patterns |

### Debug & Investigate
| Skill | Source | Description |
|-------|--------|-------------|
| `/systematic-debugging` | superpowers | 4-phase debugging workflow |
| `/investigate` | gstack | Root cause investigation (Iron Law) |

### Review & Quality
| Skill | Source | Description |
|-------|--------|-------------|
| `/review` | gstack | Staff engineer PR review |
| `/design-review` | gstack | Visual QA + atomic fix commits |
| `/cso` | gstack | OWASP+STRIDE+supply chain security audit |
| `/ai-slop-cleaner` | OMC | AI code cleanup, deletion-first |
| `/verification-before-completion` | superpowers | Evidence before claims |

### Test
| Skill | Source | Description |
|-------|--------|-------------|
| `/qa` | gstack | Browser QA testing + fix |
| `/benchmark` | gstack | Core Web Vitals before/after |
| `/mock-testing-patterns` | self | Mock gotchas, blindspot review, plugin tiers |
| `/asyncpg-testing-patterns` | self | asyncpg mock strategies |
| `/playwright-e2e-patterns` | self | Devcontainer setup, selectors, API-based |

### Ship & Deploy
| Skill | Source | Description |
|-------|--------|-------------|
| `/ship` | gstack | Test → review → PR workflow |
| `/land-and-deploy` | gstack | Merge → CI → deploy → verify |
| `/canary` | gstack | Post-deploy monitoring |

### Reflect & Learn
| Skill | Source | Description |
|-------|--------|-------------|
| `/retrospective` | self | Per-task insight extraction |
| `/retro` | gstack | Weekly cross-project retrospective |
| `/learn` | gstack | Persistent project learnings |
| `/checkpoint` | gstack | Save/resume working state |

### Safety
| Skill | Source | Description |
|-------|--------|-------------|
| `/careful` | gstack | Destructive command warnings |
| `/freeze` | gstack | Directory-scoped edit lock |

### Orchestration
| Skill | Source | Description |
|-------|--------|-------------|
| `/dispatching-parallel-agents` | superpowers | Parallel sub-agent dispatch |
| `/iterative-subagent-review-loop` | self | Fix-verify-review until zero issues |
| `/orchestrate-worktree` | self | Multi-project worktree orchestration |

### Traps & Gotchas (self, from retrospectives)
| Skill | Description |
|-------|-------------|
| `/python-mutation-traps` | Mutable defaults, dict reference detach, async concurrent modification |
| `/auth-jwt-patterns` | ES256 JWKS, 401 cascading logout, OAuth token relay |
| `/devcontainer-infra-traps` | Dotfiles history, native bindings, compose project names |
| `/asyncio-lock-non-reentrant-deadlock` | asyncio.Lock non-reentrant deadlock |
| `/fastapi-app-state-fallback-trap` | app.state getattr detached default |
| `/nextjs-middleware-origin-trap` | request.nextUrl.origin behind proxy |
| `/pytest-asyncmock-unawaited-coroutine` | AsyncMock teardown RuntimeWarning |
| `/pytest-coverage-gotchas` | Fractional coverage, ASGI 0% |
| `/e2e-mock-shape-drift` | Wrong mock API shape passes silently |
| `/test-against-source-contracts` | Verify tests match actual contracts |
| `/uv-git-dependency-cache-trap` | uv aggressive git dep caching |
| `/alembic-postgres-enum-migration` | ALTER TYPE in transaction fails |
| `/stitch-code-bidirectional-sync` | Stitch nav inconsistency across screens |

### Utility
| Skill | Source | Description |
|-------|--------|-------------|
| `/mermaid` | self | Mermaid diagram generation (23 types) |
| `/content-blog-post` | self | bsvibe.dev blog post writing |
| `/analysis-cost-report` | self | BSGateway cost analysis |

### Architecture
| Skill | Source | Description |
|-------|--------|-------------|
| `/bsvibe-auth-centralization` | self | Central auth.bsvibe.dev pattern |
| `/large-codebase-deprecation-removal` | self | Graceful deprecation lifecycle |
| `/sqlalchemy-model-refactoring-patterns` | self | Field removal & migration cascades |

## Credits

Skills adapted from open-source projects:
- [obra/superpowers](https://github.com/obra/superpowers) — systematic-debugging, test-driven-development, verification-before-completion, dispatching-parallel-agents, writing-plans
- [garrytan/gstack](https://github.com/garrytan/gstack) — cso, careful, freeze, office-hours, investigate, review, ship, land-and-deploy, qa, benchmark, canary, retro, checkpoint, learn, plan-eng-review, plan-design-review, autoplan, design-review
- [Yeachan-Heo/oh-my-claudecode](https://github.com/Yeachan-Heo/oh-my-claudecode) — deep-interview, ai-slop-cleaner
