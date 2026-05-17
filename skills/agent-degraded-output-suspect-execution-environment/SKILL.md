---
name: agent-degraded-output-suspect-execution-environment
description: When a capable agent first declares a STRONG plan/contract/approach then a retry or continuation produces a WEAKER one, suspect the execution environment couldn't run the strong version — not model laziness or a prompting gap.
---

# Agent declares strong, then degrades → suspect the execution environment

## Problem

An LLM agent with a declare→execute split (declares a verification
contract / a plan / a tool sequence, then carries it out) produces a
**weak** final artifact. The obvious first hypothesis — "the model is
lazy / the prompt is too soft / it doesn't follow instructions" — is
often **wrong**.

- 증상: the agent declares something strong (`pytest`, a real test
  command, a thorough plan), the run fails or hits a round cap, and a
  retry / continuation re-declares a **weaker** version (`py_compile`,
  an `import`-only check, a trivial plan) that *does* pass.
- 근본 원인: the strong version was **un-runnable in the agent's
  execution environment** — a missing toolchain, a read-only path, a
  permission wall, a placeholder that didn't resolve. The agent ran
  the strong command, saw it fail, and *rationally* degraded to
  something the broken environment could satisfy.
- 흔한 오해: blaming prompt strength → you strengthen the prompt, the
  agent declares strong AGAIN, it still can't run it, and it degrades
  AGAIN. Prompt engineering cannot fix an environmental wall.

Real case (BSNexus, 2026-05): the work LLM's `shell_exec` ran in a
backend container with no `pytest`/`ruff`. qwen3 declared a strong
`pytest` contract (A1 prompt work succeeded), spent 36 rounds unable
to run it (`pip install` blocked — read-only site-packages), hit the
loop cap; the Tier-1 continuation then re-declared an `import`-only
contract that matched the broken environment. The deliverable reached
`verified` with its tests never run. The fix was environmental (give
the work phase the toolchain — a sandbox), not prompting.

## Solution

When you see declare-strong-then-degrade, **diagnose the environment
before touching the prompt**:

1. Take the STRONG thing the agent declared on the first attempt and
   run it *yourself*, by hand, in the exact environment the agent
   runs in (same container, same user, same cwd, same PATH).
2. If it fails — missing binary (exit 127), `Permission denied`,
   read-only FS, an unresolved `<placeholder>` token — that is the
   root cause. The agent isn't lazy; it's adapting to a broken env.
3. Fix the environment (install the toolchain, fix ownership, resolve
   the placeholder, mount the volume) — not the prompt.
4. Re-verify: the agent should now declare strong AND the strong
   version should run.

Inspect the agent's tool-call trace (e.g. `tool_events`): a run that
shows the agent *trying* the strong command, getting errors, then
`pip install` attempts, then falling back — is the signature.

## Key Insights

- A capable agent degrading its own output is usually **rational
  adaptation to a broken environment**, not a compliance failure. The
  agent saw the strong path fail and routed around it.
- The declare→execute split makes this sneaky: the *declaration* looks
  fine (prompt worked), so you don't suspect the prompt is innocent.
  The break is between declare and execute.
- Prompt engineering has a hard ceiling here — re-nudging a model to
  declare strong does nothing when the environment can't run strong.
  Same family as `local-llm-runtime-nudge-ceiling`.
- First diagnostic move: **run the agent's own first-attempt strong
  command by hand in its environment.** One command tells you env-vs-
  prompt.

## Red Flags

- A retry / continuation / fallback attempt produces a *simpler* or
  *weaker* artifact than the first attempt.
- The agent's trace shows it tried tool/command X, got an error, then
  switched to a weaker Y.
- `pip install` / `npm install` / `apt` attempts mid-run (the agent
  is trying to repair a missing toolchain itself).
- "The model just won't do X" after you've already strengthened the
  prompt once.
- A verification / gate passes via a check that doesn't actually
  exercise the deliverable (compile-only, import-only, `--help`).
