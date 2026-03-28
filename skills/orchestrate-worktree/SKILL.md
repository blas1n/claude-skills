---
name: orchestrate-worktree
description: Multi-project worktree orchestration with Ralph Loop — create worktrees, run tasks via claude -p in devcontainers, review until 0 issues, push & PR
---

# Orchestrate Worktree

Multi-project worktree orchestration using Ralph Loop pattern.
Creates worktrees, decomposes work into tasks, runs `claude -p` in devcontainers with fresh context per iteration, reviews until zero issues, then ships PRs.

## Input Format

User provides project-task pairs:
```
/orchestrate-worktree
bloasis: logging → structlog 마이그레이션
MetaSummarizer: 테스트 80%+ 달성
BSage: WebSocket auth 수정 + CORS 설정 가능화
```

## Workflow (6 Phases)

### Phase 1: Plan

For each project-task pair:

1. **Explore** the project codebase to understand scope (use Explore agents in parallel)
2. **Decompose** the work into tasks small enough for one context window
3. **Generate `tasks.json`** — last task is ALWAYS a code review task
4. **Determine** if devcontainer is needed (DB/Redis dependent tests → yes)

**tasks.json format:**
```json
{
  "branchName": "fix/structlog-migration",
  "tasks": [
    {
      "id": "TASK-001",
      "title": "Add structlog dependency and create config",
      "description": "Detailed implementation instructions",
      "acceptanceCriteria": "uv run ruff check passes, structlog in pyproject.toml",
      "passes": false,
      "priority": 1
    },
    {
      "id": "REVIEW-001",
      "title": "Code review — fix all issues including minor ones",
      "description": "Review git diff main, find security/quality/test/style issues, fix them. If issues found, add new REVIEW tasks. Mark passes:true only when 0 issues remain.",
      "acceptanceCriteria": "Zero issues found in review, all checks pass",
      "passes": false,
      "priority": 99
    }
  ]
}
```

**Rules for task decomposition:**
- Each task must be completable in a single `claude -p` invocation
- Tasks are ordered by dependency (priority number)
- Review task always has highest priority number (runs last)
- Include `acceptanceCriteria` for verification

### Phase 2: Setup

For each project, run in parallel:

```bash
# 1. Create worktree (auto-assigns port slot)
~/Works/_infra/scripts/create-worktree.sh <project> <branch>

# 2. Start devcontainer
dc-up <project> <branch-sanitized>

# 3. Place .agent/ files in worktree
mkdir -p ~/Works/<project>/wt/<branch>/.agent
# Write tasks.json and initial progress.txt
```

**PROMPT.md** — placed in `.agent/PROMPT.md`, injected into each `claude -p` call:
```
You are a developer working on this project.

Read .agent/tasks.json and select the highest-priority task where passes is false.
Implement it according to the description and acceptanceCriteria.

After implementation:
1. Verify: uv run ruff check . && uv run ruff format --check . && uv run pytest
2. If verification passes: git commit with descriptive message
3. Update .agent/tasks.json: set passes to true for the completed task
4. Append findings/learnings to .agent/progress.txt

For REVIEW tasks:
- Run git diff main and review ALL changes
- Check: security, code quality, type hints, test quality, architecture rules, bugs, style
- If issues found: fix them, then add a NEW review task to tasks.json (passes:false)
- Only mark passes:true when ZERO issues remain (including minor ones)

IMPORTANT: Only work on ONE task per invocation. Do not skip ahead.
```

### Phase 3: Ralph Loop

Run `ralph-loop.sh` for each project (in parallel where possible):

```bash
~/Works/_infra/scripts/ralph-loop.sh <compose_project> <workspace_folder>
```

**ralph-loop.sh behavior:**
- While `tasks.json` has any `passes: false` task:
  1. Run fresh `claude -p` with PROMPT.md (devcontainer exec, `--allowedTools`)
  2. Claude picks one task, implements, verifies, commits, updates tasks.json
  3. Log iteration number, task ID, duration to stdout
- When all tasks have `passes: true`: exit successfully
- Safety: if same task fails 3 consecutive iterations, abort with error

### Phase 4: Verify

Run `pre-push-verify.sh` for each project:

```bash
~/Works/_infra/scripts/pre-push-verify.sh <compose_project> <workspace_folder>
```

Checks: ruff lint + ruff format + pytest + commit author (host global git config)

### Phase 5: Ship

For each project:
```bash
git push -u origin <branch>
gh pr create --title "<title>" --body "<english PR body with summary + test plan>"
```

**PR body format:**
```markdown
## Summary
- Bullet points describing changes

## Test plan
- [x] Verification items

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

### Phase 6: Retrospective

After all projects are shipped:
1. Run `/retrospective` to capture learnings as reusable skills
2. Generate a final report:

```markdown
## Orchestration Report

| Project | Branch | Tasks | Ralph Iterations | Issues Fixed | Coverage |
|---------|--------|-------|-----------------|-------------|----------|
| bloasis | fix/structlog-migration | 5 | 8 | 3 | 95.7% |
| ...     | ...    | ...   | ...             | ...         | ...      |

### Key Findings
- ...

### New Skills Created
- ...
```

## Critical Rules

1. **`--allowedTools "Edit,Write,Bash,Read,Glob,Grep"`** — always include with `claude -p`
2. **Commit author** — use host's `git config --global user.name/email`
3. **PR body** — always in English
4. **Review** — continues until 0 issues (no minor issues tolerated)
5. **Fresh context** — each Ralph Loop iteration gets a clean `claude -p` instance
6. **State via files** — `tasks.json` and `progress.txt` are the only memory between iterations
7. **One task per iteration** — never let claude work on multiple tasks in one invocation
8. **pre-push-verify must pass** before any push

## Infrastructure Dependencies

| Script | Location | Purpose |
|--------|----------|---------|
| `create-worktree.sh` | `~/Works/_infra/scripts/` | Worktree + port allocation |
| `ralph-loop.sh` | `~/Works/_infra/scripts/` | Ralph Loop execution engine |
| `pre-push-verify.sh` | `~/Works/_infra/scripts/` | Pre-push gate |
| `dc-up` / `dc-exec` | `~/.zshrc` functions | Devcontainer management |

## When to Use This Skill

- Multiple projects need similar fixes (security, linting, test coverage)
- Cross-project refactoring or migration
- Batch code review and hardening
- Any work that spans multiple repos and benefits from parallel execution
