---
name: iterative-subagent-review-loop
description: "Use when reviewing and hardening a branch before merge. Runs a fix→verify→sub-agent-review loop until zero issues remain. Effective for large branches (10+ files) where single-pass review misses integration bugs."
---

# Iterative Sub-Agent Review Loop

## Problem

Large branches (10+ changed files, multiple new modules) cannot be reliably reviewed in a single pass. Each fix can reveal new issues that were previously masked. A single reviewer also develops blind spots after extended context.

## When to Apply

- Branch review with 10+ changed files
- New module integration (multiple modules wiring together)
- Pre-merge hardening when quality bar is high
- User requests "리뷰 후 수정까지" or "이슈 없을 때까지"

## Loop Protocol

```
Round N:
  1. FIX    — Apply all known fixes (Edit)
  2. VERIFY — Run linter + formatter + tests (Bash)
     - ruff check, ruff format --check, pytest --cov
     - ALL must pass before proceeding
  3. REVIEW — Launch Explore sub-agent with fresh context (Agent)
     - Sub-agent gets NO prior conversation context
     - Must read actual files, not rely on prior round's findings
     - Explicitly list what was already fixed (prevents re-reporting)
  4. ASSESS — Evaluate sub-agent findings
     - New issues found → Round N+1
     - NO ISSUES FOUND → Exit loop, commit
```

## Sub-Agent Prompt Template

Each round's review agent prompt MUST include:

1. **Previously fixed list** — Prevents re-reporting known fixes
2. **Current status** — Test count, coverage %, ruff status
3. **Specific file list** — Key files to read (not "review everything")
4. **Severity filter** — "Only report REAL issues that cause crashes, data corruption, or security vulnerabilities"
5. **Exit condition** — "State NO ISSUES FOUND if nothing real remains"

### Round 1 (Initial Review) — Parallel Agents

For the first round, launch up to 3 Explore agents in parallel by domain:

```
Agent 1: Core/infrastructure files (config, scheduler, dependencies, maintenance)
Agent 2: Domain logic files (garden modules — new features being reviewed)
Agent 3: Test files (coverage, mock quality, missing edge cases)
```

This maximizes coverage while keeping each agent's scope focused.

### Round 2+ (Targeted Review) — Single Agent

After fixes, launch 1 agent with:
- Full list of what was fixed
- Instruction to verify fixes AND find new issues
- Increasingly strict severity filter each round

## Escalation Pattern

Narrow the scope and raise the bar each round:

| Round | Agent count | Scope | Severity filter |
|-------|------------|-------|-----------------|
| 1 | 2-3 parallel | Full branch by domain | All issues |
| 2 | 1 | Files touched + dependencies | Critical + Medium |
| 3 | 1 | Key integration points only | Critical only |
| 4+ | 1 | Specific files from prior finding | "Only runtime crashes" |

## Key Principles

### Fresh Context is Critical
Each sub-agent starts with zero prior context. This is a **feature** — it avoids confirmation bias. The agent must read actual code, not inherited assumptions.

### List What Was Fixed
Without this, agents waste time re-reporting known fixes. Always prefix with:
> "Previously fixed in Round N: [numbered list]"

### Verify Before Review
Never send code to review that doesn't pass lint/tests. The agent will report lint noise instead of real bugs.

### Trust the Exit Condition
When the agent says "NO ISSUES FOUND" after being told to be strict, trust it. Diminishing returns set in after Round 4-5.

## Anti-Patterns

- **Skipping verification between rounds** — Leads to cascading failures in review
- **Not listing prior fixes** — Agent re-reports same issues, wasting a round
- **Too-broad review scope in late rounds** — Agent invents style concerns when no real bugs exist
- **Fixing during review** — Fix and review are separate phases; mixing them causes confusion

## Origin

Developed during BSage v2.2 branch review (2026-03-17). 5 rounds were needed for a 53-file branch. Each round discovered 1 critical bug that previous rounds missed, demonstrating that single-pass review is insufficient for large integration branches.
