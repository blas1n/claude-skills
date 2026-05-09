---
name: local-llm-agent-safety-nets
description: When building multi-turn agent / tool-calling systems on local/smaller LLMs (Qwen3, gpt-oss, Llama family), never rely on prompt compliance for safety-critical operations. Add backend safety nets — auto-bootstrap missing state, recover misnamed tool calls from arg shape, derive verification from workspace state. Triggers — local Ollama agent stalls on turn 1, hits round-cap with no deliverable, "MAY do X" directives fire only sometimes, model emits one tool name for everything.
category: trap
---

# Local LLM Agent Safety Nets

## Core Lesson

Prompt directives like **"MAY"**, **"if X then do Y"**, or **"bootstrap exception:"** are interpreted weakly by local models (Qwen3-class, gpt-oss, small Llamas). Instruction following is noticeably worse than frontier cloud models.

**If a multi-turn agent scenario depends on exactly one agent emitting a specific marker/tool-call to unblock the next turn, it will deadlock.**

Design backend safety nets that guarantee the invariant regardless of what the LLM does.

## When This Bites

- Turn 1 of any scenario where the first agent must bootstrap state (first phase, first task, first screen).
- Conditional prompt rules like "if no phase exists yet, you may emit `[CREATE_PHASE ...]`".
- Any path where the backend raises `No X exists yet` and the LLM is expected to fix it with a tool call.

Symptom: scenario stalls at 0 phases / 0 tasks with `marker_task_creation_failed: No phase exists yet` errors in a loop.

## Pattern — Backend Auto-Bootstrap

```python
# Pseudocode. In your marker/tool handler, AFTER parsing the LLM output:
if task_markers and not any(a.get("tool") == "create_phase" for a in actions):
    # LLM gave us tasks but didn't create a phase. Check DB state directly.
    existing = await db.scalar(
        select(func.count(Phase.id)).where(Phase.project_id == project_id)
    )
    if existing == 0:
        # Safety net — create a default phase so tasks can attach.
        await create_phase(name="기획", description="...자동 생성", ...)
        actions.append({"tool": "create_phase", ...})
        logger.info("phase_auto_bootstrapped", agent=..., task_count=...)
```

Rules:
- Fire only when the invariant is **currently broken** (check count, not just "is it the first turn").
- Use a boring default ("Planning", "General", "기획") — it exists to unblock, not to be semantically perfect.
- Log distinctively (`_auto_bootstrapped`) so you can count how often the LLM needed rescue.
- Keep the LLM-compliant path too — if it DOES emit `[CREATE_PHASE ...]`, let that win.

## Anti-Pattern — Relying on Prompt Escalation

Tried and failed in this order:

1. `"Do NOT create phases."` — subordinate obeyed, no phase ever created.
2. `"**BOOTSTRAP EXCEPTION:** you MAY open ONE [CREATE_PHASE ...] on the first turn."` — Qwen3 still emitted only CREATE_TASK markers.
3. Stronger imperative: `"You MUST emit [CREATE_PHASE ...] when no phase exists."` — still unreliable, probably ~60% compliance.

No amount of prompt strengthening fixes this reliably on Qwen3-class. The model follows the *main* instruction block (create tasks, delegate) and drops the conditional edge case.

## Where Safety Nets Go

- **Marker/tool-call handler** — after parsing, before persisting, check invariants.
- **Entity-creation tool** (e.g. `create_task`) — if it raises "No parent X exists", catch and auto-create X with a default before retrying (optional second layer).
- **Dispatcher tick** — once per loop, reconcile invariants (e.g. every active project has ≥1 phase).

Choose the innermost location that still has enough context. In my case: the marker handler, because only it knows the agent's intent (`CREATE_TASK` emitted) and the project context simultaneously.

## Writing the Test First

The red test that catches the deadlock:

```python
async def test_execute_markers_auto_bootstraps_phase_for_tasks(...):
    """When CREATE_TASK arrives for a project with no phase, backend
    auto-creates one. Without this, Qwen3 scenarios deadlock on turn 1."""
    # Seed project + agents, NO phase.
    text = '[CREATE_TASK title="..." assignee="..."]'
    actions = await _execute_inline_markers(text, ...)
    phase_actions = [a for a in actions if a["tool"] == "create_phase"]
    task_actions = [a for a in actions if a["tool"] == "create_task"]
    assert len(phase_actions) == 1  # auto-bootstrap fired
    assert len(task_actions) >= 1   # task attached successfully
```

Pair with a negative test: when a phase already exists, auto-bootstrap must NOT fire (it's a one-shot safety net, not per-turn).

## Real Example — BSNexus Session 9

- **Before**: Phase-gate restricted `[CREATE_PHASE]` to org-root agents. Longrun E2E @mentions CMO first (subordinate). CMO emits 6 CREATE_TASK markers. All fail: `No phase exists yet`. Scenario stalls at 0/0 for 30+ min.
- **Prompt fix attempt**: add subordinate-only rule `"if no phase exists, you MAY emit [CREATE_PHASE ...]"`. Qwen3-coder:30b ignored it.
- **Backend safety net**: `phase_auto_bootstrapped` — if task markers arrive and phase_count == 0, auto-create "기획" phase. Scenario ran to completion (CHAIN_COMPLETE, 35.6 min, 22 tasks done).

## Real Example — BSNexus PR11 (qwen3-coder tool-name collapse)

Different shape of weak compliance: the model called the right tool **content** under the wrong **name**.

- **Symptom**: easy scenario (`add(a,b)` + pytest) hit the round-cap with no deliverable. Smoke + medium passed; only easy stuck.
- **Initial diagnosis**: "model skips `file_write`." Wrong.
- **Activity-log inspection (per-round)**: model emitted `shell_exec` for *every* call, including ones with `{path, content}` args (clearly file_write payloads). Local dispatch ran the JSON as a shell command, failed, the model retried, looped to round-cap.
- **Backend safety net**: `recover_misnamed_local_tool(name, args) → (name, note)` — when args are *unambiguously* shaped for another known local tool, rewrite the name before dispatch:

  ```python
  # tools.py
  def recover_misnamed_local_tool(name, args):
      has_command = isinstance(args.get("command"), str) and args["command"].strip()
      has_path = isinstance(args.get("path"), str) and args["path"].strip()
      has_content = isinstance(args.get("content"), str)  # empty string legal
      if name == "shell_exec" and not has_command:
          if has_path and has_content:
              return "file_write", "shell_exec→file_write (path+content, no command)"
          if has_path:
              return "file_read", "shell_exec→file_read (path only, no command)"
      if name == "file_write" and has_command and not (has_path and has_content):
          return "shell_exec", "file_write→shell_exec (command, no path+content)"
      return name, None
  ```

  Applied at both the dispatch-routing layer (so local-vs-MCP routing is honest) and inside `execute_tool_call` (defence-in-depth). Logged as `tool_name_recovered` with original/recovered/note for observability.

- **Result**: easy went 0/N → ✅ 24.5s end-to-end (Direction → file_write → shell_exec pytest → derived verification → SubprocessVerifier → `proof_state=verified`).

### Companion finding — round-cap output guard ignored nested storage

Same PR, separate failure mode: the round-cap path transitioned the run to `blocked` but `publish_run_output` bailed because its empty-output guard checked only `summary / inline / files` — none of which see the *nested* `local_tool_log.written_files` where the dispatcher folds tool history. Fix: widen the guard to count `local_tool_log` as publishable. Pattern: **when the dispatcher writes work into a nested key, every downstream gate must know about that key** — easy to miss when the gate predates the nested storage.

## Pattern Family — recover, don't re-prompt

The meta-rule: if the model's *intent* is recoverable from observable evidence (DB state, tool args, written files), do the recovery server-side. Don't add another sentence to the prompt — local 30B coders won't read it. The trio so far:

1. **State-bootstrap** — DB count is 0 + LLM gave dependent action → auto-create the missing parent (BSNexus session 9).
2. **Action-shape recovery** — tool name wrong but args unambiguous → rewrite name (BSNexus PR11).
3. **Workspace derivation** — LLM didn't run the verifier but wrote test files → synthesize `pytest <files>` (BSNexus PR11, third-tier verification derive).

All three replace "convince the model harder" with "infer from what actually happened." See also `local-llm-runtime-nudge-ceiling`.

## Heuristic

When reviewing a multi-turn agent design, ask:
> *"If the LLM silently drops this conditional instruction, does the system recover, or does it deadlock?"*

If it deadlocks → safety net required.

Second pass — also ask:
> *"If the LLM does the right action under the wrong name (or the wrong action under the right name), does the system recover, or loop?"*

If it loops → arg-shape recovery required.

Safety nets cost ~20 lines of code per invariant. Debugging a stall in a 30-minute E2E costs much more.

## Debugging hygiene — inspect per-round activity log before re-prompting

PR11 iter 3 wasted a 10-minute dogfood iteration because the assumed diagnosis ("model skips `file_write`") was almost-but-not-quite right. The real issue ("model misnames `file_write` as `shell_exec`") only showed up after dumping the per-round `tool_call_start` entries with full args. **Before iterating on the prompt, dump the raw tool-call sequence — name + args excerpt + round_idx — and look for misnaming, repetition, and arg-shape mismatch.** The prompt is rarely the leverage point; the dispatcher is.
