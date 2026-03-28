---
name: iterative-subagent-review-loop
description: "Use when reviewing and hardening a branch before merge. Runs a fix→verify→sub-agent-review loop until zero issues remain. Effective for large branches (10+ files) where single-pass review misses integration bugs."
version: 1.0.0
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

## Severity Strategy

### Default: All-Severity with Reproduction Requirement

The user's goal is to fix ALL issues including minor ones. The escalation pattern (raising severity bar each round) is wrong for this — it hides minor issues that the user wants fixed.

Instead, use **category rotation** with a constant reproduction requirement:

| Round | Agent count | Category | Instruction |
|-------|------------|----------|-------------|
| 1 | 2-3 parallel | Full branch (split by domain) | "All severities. Each issue MUST include a concrete reproduction scenario" |
| 2 | 1-2 | Files modified in Round 1 + dependents | "Verify fixes + find new issues. Reproduction scenario required" |
| 3 | 1 | Full branch | "Only issues NOT caught in Rounds 1-2. Reproduction scenario required" |
| 4+ | 1 | Full branch | "Target: ZERO ISSUES. Report if found, otherwise 'No issues found'" |

**Key difference from escalation:** Severity filter stays at ALL. The reproduction scenario requirement naturally filters out false positives — style suggestions and theoretical concerns cannot produce a concrete "step 1, step 2, crash" scenario, so they self-eliminate.

### Alternative: Escalation (when fast merge is the priority)

Use when the user wants to merge quickly and only cares about critical bugs:

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
- **Trusting agent diagnosis without verification** — See "Fix Validation" below

## Fix Validation: Never Trust Diagnosis Blindly

**Problem observed (2026-03-21):** Agent reported `bisect_right` as a bug and suggested `bisect_left`. The fix was applied, but `bisect_left` was actually WRONG — it introduced a range inversion bug. A subsequent sub-agent review caught this.

**Root cause:** The reviewing agent's reasoning about boundary semantics was backwards. The fixer (me) accepted the diagnosis without independently verifying the logic.

**Rule: Before applying any fix involving algorithmic logic (bisect, sort, index math, boundary conditions):**

1. **Construct a concrete example** with exact numbers (don't reason abstractly)
2. **Trace both the current AND proposed code** through that example
3. **Include a boundary-exact test case** (value == boundary) in the verification
4. If the fix "obviously makes sense" but you haven't traced an example, STOP — that's when mistakes happen

This applies especially to:
- bisect_left vs bisect_right
- Off-by-one in range/slice
- Inclusive vs exclusive bounds
- Coordinate system conversions
- API parameter semantics (e.g., `latest` vs `oldest` in pagination APIs)

### Wrong Diagnosis, Right Area

**Problem observed (2026-03-21):** Agent diagnosed Slack `latest_ts` loop as tracking the wrong value (oldest instead of newest). Code tracing proved the diagnosis WRONG — the loop correctly ends at newest after reversing. But investigating the area revealed the REAL bug: `params["latest"]` should be `params["oldest"]` (Slack API semantics — `latest` = upper bound, `oldest` = lower bound for forward polling).

**Lesson:** When an agent flags a specific area but the diagnosis doesn't hold up under tracing, **don't dismiss the area**. The agent's attention was drawn there for a reason. Investigate the surrounding code for a different bug in the same region.

**Pattern:** Wrong diagnosis → trace and disprove → keep investigating the flagged area → find real bug nearby.

## Cross-Session Review Inconsistency

**Problem observed (2026-03-21):** After a session declared "zero issues found" with 2 sub-agents, a NEW session found 11 more issues on the same code.

**Why this happens:**
- Each session's sub-agents have different "attention patterns" — they notice different things
- Previous session's "no issues" was relative to its severity threshold and prompt framing
- New session starts fresh with no knowledge of what was already reviewed

**Mitigation — Attention Angle Rotation:**

Each session should use a DIFFERENT review angle. Proven angles that each find unique bugs:

| Session | Angle | What it uniquely finds |
|---------|-------|----------------------|
| 1 | Security + robustness | Injection, crash paths, missing validation |
| 2 | Data integrity + async | Race conditions, TOCTOU, lock correctness |
| 3 | Integration seams | Mock drift, API type mismatch, fixture accuracy |
| 4 | Error handling symmetry | Sibling methods catching different exceptions |
| 5 | Operational correctness | Pagination direction, timeout values, idempotency |
| 6 | Logic bugs in plain sight | Wrong comparison operators, inverted conditions, off-by-one |

**Additional mitigations:**
1. **Anchor reviews to a checklist**, not open-ended "find bugs" prompts. The angle table above provides the checklist.
2. **Record what was verified** in commit messages or PR descriptions — so the next reviewer knows what's been checked
3. **Accept diminishing returns** — after 3 clean rounds with strict criteria, additional reviews find style issues, not bugs

### False Positive Escalation in Late Sessions

**Problem observed (2026-03-21):** As real bugs decrease across sessions, agents feel pressure to "find something" and report increasingly theoretical concerns. False positive rate: ~30% in early sessions → ~70%+ in late sessions.

**Symptoms:**
- Agent reports issues in files NOT on the branch
- Agent flags patterns that are "not ideal" but can't produce a reproduction scenario
- Agent re-reports fixed issues with slightly different framing
- Agent discovers the same thing is "already safe" after extended analysis

**Rule:** In sessions 4+, explicitly tell the agent: "If you find NO real issues, that is the CORRECT answer. Do not manufacture concerns." Trust the exit condition.

## Origin

Developed during BSage v2.2 branch review (2026-03-17). 5 rounds were needed for a 53-file branch. Each round discovered 1 critical bug that previous rounds missed, demonstrating that single-pass review is insufficient for large integration branches.

Updated 2026-03-21 after feature/resource branch review (10+ rounds). Key addition: fix validation rule (never apply algorithmic fixes without concrete trace) and cross-session inconsistency mitigation.

Updated 2026-03-21 after feature/agent branch review (6 sessions, 20 sub-agents, 15 fixes). Key additions: wrong-diagnosis-right-area pattern, attention angle rotation table, false positive escalation in late sessions.
