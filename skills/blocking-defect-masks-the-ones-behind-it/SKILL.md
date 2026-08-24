---
name: blocking-defect-masks-the-ones-behind-it
description: When a defect stops execution entirely, every defect downstream of it is invisible — so a fix is not a checkmark but a probe. Re-prove in production after EACH fix instead of planning the whole repair up front; expect the next layer to appear only once the blocker is gone.
version: 1.0.0
task_types: [debug, verification, refactor]
triggers:
  - pattern: "a production fix is deployed and about to be called done"
  - pattern: "planning a multi-part repair for a defect that stops execution"
  - pattern: "unit tests and CI are green but production behaviour is unknown"
---

# A blocking defect hides the ones behind it

## Problem

One founder judgment — *"the agent must never use the CLI's native tools"* — turned into **four
production defects**, discovered one at a time, each invisible until the one in front of it was
removed:

| # | Defect | Became visible only after |
|---|---|---|
| 1 | Agent was given the CLI's native tools instead of the platform's | the founder's judgment |
| 2 | The vendor built-in denylist had rotted — **every** agent run was aborting | #1 shipped, so a turn could start |
| 3 | The tool transport re-provisioned the workspace on **every tool call** | #2 shipped, so tool calls actually happened |
| 4 | The agent's commands got no secrets (a parity gap vs the verification gate) | #3 shipped, so commands actually ran |

Every one of the four passed unit tests and CI. Every one was found by running the real thing in
production and reading the worker log.

The trap is not "we missed some bugs." It is that **the list could not have been written up front.**
Defect 2 could not be observed while defect 1 prevented the agent from holding any tool. Defect 4
could not be observed while defect 2 prevented the turn from starting at all. A blocking defect is
an opaque wall: everything behind it reads as "fine" because nothing behind it executes.

- Symptom: a fix ships, and the very next production run fails for a *different* reason — repeatedly.
- Root cause: execution stops at the first blocker, so downstream code paths produce **no signal
  at all** — neither success nor failure. Absence of a failure is read as absence of a defect.
- Common misunderstanding: *"CI is green and the fix is deployed, so this is done."* Green means
  the paths the tests exercise are fine. It says nothing about paths that production alone reaches.
- Second misunderstanding: *"let me plan the full repair, then execute it."* You cannot enumerate
  what you cannot observe. Planning past the blocker is guessing.

## Solution

Treat each fix as a **probe**, not a completion:

1. **Ship the blocker fix alone.** Do not bundle speculative downstream fixes — you do not yet know
   what is behind the wall.
2. **Re-run the real thing in production immediately**, with the *same input* that failed. Same
   input is what makes before/after comparable.
3. **Read the execution log, not the status field.** A run can settle "successfully" while producing
   nothing. Count the artifact the work exists to produce (deliverables, rows, files) — and count the
   *mechanism* too (tool calls, dispatched commands, env names carried).
4. **Expect a new failure and treat it as progress.** A different failure means the wall moved.
   The same failure means the fix did not reach production (check every execution surface — see
   below).
5. **Repeat until the artifact appears.** Only the artifact closes the loop.

### The comparison table is the deliverable

Keep a running before/after of *mechanism*, not just outcome. This is what makes each step provable:

| | before | after |
|---|---|---|
| tool calls | **0** | many |
| secrets carried | `env_names=[]` | 5 names |
| artifacts produced | **0** | 1, values matching a local control run |

A local control run — the same command executed by hand where it is known to work — is what proves
the produced values are real rather than fabricated.

### Check every execution surface before concluding "the fix didn't work"

A deploy marker (`/api/health` `git_sha`, image tag) usually covers **one** process. Code that runs
in a different process — a host agent, a worker daemon, a sidecar — may not be redeployed by the
same mechanism. Confirm the fixed code is actually loaded *where it runs* before diagnosing further.
Mistaking "not deployed there" for "fix doesn't work" sends the whole investigation the wrong way.

## Why this matters

The instinct after a fix is to declare victory and move on, because each individual fix genuinely
was correct. But when the defect class is *blocking*, shipping one fix does not reduce the unknown
count — it **reveals** it. Stopping at the first green run leaves the remaining layers in
production, still invisible, waiting for the next real user.

Conversely, this is why "we fixed it three times and it's still broken" is not necessarily
incompetence: with a stack of masked defects, three fixes and three new failures is exactly what
progress looks like. Say so plainly, with the mechanism table, rather than hedging.

## Related

- `verification-before-completion` — evidence before claims
- `wiring-guard-must-cut-the-wire-not-just-the-endpoint` — guards must break the wire, not the endpoint
- `unit-test-supplies-what-production-withholds` — green units over a dead production path
