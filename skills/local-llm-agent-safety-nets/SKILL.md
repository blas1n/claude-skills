---
name: local-llm-agent-safety-nets
description: When building multi-turn agent systems on local/smaller LLMs (Qwen3, gpt-oss, Llama family), never rely on prompt compliance for safety-critical operations. Add backend safety nets for bootstrap/invariants. Triggers — agent system uses local Ollama model, scenario stalls on turn 1, "MAY do X" prompt directives fire only sometimes.
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

## Heuristic

When reviewing a multi-turn agent design, ask:
> *"If the LLM silently drops this conditional instruction, does the system recover, or does it deadlock?"*

If it deadlocks → safety net required.

Safety nets cost ~20 lines of code per invariant. Debugging a stall in a 30-minute E2E costs much more.
