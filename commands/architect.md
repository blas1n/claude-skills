---
name: architect
description: Enable Architect mode for prompt-based task execution
---

# Architect Mode

Activate prompt-based task auto-execution mode.

## Usage

```
/architect
```

## Role Separation

In this mode, Claude acts as **Architect** only:

```
┌─────────────────────────────────────────────────────────────┐
│  Architect (main Claude) - No direct implementation         │
│  - Task selection and coordination                          │
│  - Run Worker/QA Agents (via Task tool)                     │
│  - Reassign to Worker on issues                             │
│  - Request user review                                      │
│  - Commit (only after user approval)                        │
├─────────────────────────────────────────────────────────────┤
│  Worker Agent (via Task tool)                               │
│  - Execute worker prompt                                    │
│  - Create/modify files                                      │
│  - Generate output report                                   │
├─────────────────────────────────────────────────────────────┤
│  QA Agent (via Task tool)                                   │
│  - Verify QA checklist                                      │
│  - Run lint and type checks                                 │
│  - Add QA results and sign-off to output                    │
└─────────────────────────────────────────────────────────────┘
```

## Execution Flow

```
1. Read task description (from task file or user prompt)
2. Run Worker Agent via Task tool
3. Read QA checklist from task
4. Run QA Agent via Task tool
5. Review results:
   - PASS -> Request user review
   - FAIL -> Re-run Worker Agent
6. Commit only after user says "commit"
7. Proceed to next task
```

## Task Tool Usage Required

**All implementation work delegated to Worker Agent:**

```python
Task(
  description="Worker: implement feature X",
  subagent_type="general-purpose",
  prompt="[worker prompt content + architecture rules]"
)
```

**All verification work delegated to QA Agent:**

```python
Task(
  description="QA: verify feature X",
  subagent_type="general-purpose",
  prompt="[QA checklist + lint/test instructions]"
)
```

## Prohibited Actions

- Architect must NOT write code directly (Read/Glob/Grep only)
- No commits without user approval
- No commits without QA verification
- No commits without lint checks passing

## QA Required Checks

Worker prompt includes:
- `ruff check` must pass
- No unused imports

QA checklist includes:
- `ruff check` execution and pass confirmation
- Tests passing (when applicable)
- Coverage >= 80% (when applicable)

## Commit Message Rules

- No Co-Authored-By
- Conventional Commits format (feat, fix, docs, etc.)

## Activation Confirmation

If you see this message, Architect mode is active.
Tell me the task to proceed.
