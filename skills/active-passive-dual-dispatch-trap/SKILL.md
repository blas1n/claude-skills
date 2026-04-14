---
name: active-passive-dual-dispatch-trap
description: Agent systems with active (planning) and passive (execution) modes can dual-dispatch the same agent, causing it to plan instead of execute
version: 1.0.0
task_types: [debugging, design]
triggers:
  - pattern: "agent creates tasks but never executes them, or agent only plans without producing artifacts"
---

# Active/Passive Dual Dispatch Trap

## The Pattern

In multi-agent systems with separate **active mode** (planning/delegation tools) and **passive mode** (execution tools like file_write), the same agent can be dispatched in both modes simultaneously.

## The Trap

```
User → CMO (active) → @mentions Backend_Engineer
                         ↓
         Two things happen at the same time:
         1. Active delegation: Backend_Engineer dispatched in ACTIVE mode
            → gets create_task, create_phase tools (NO file_write)
         2. GlobalDispatcher: finds pending task assigned to Backend_Engineer
            → dispatches in PASSIVE mode (file_write, claim_task)

         Active mode runs FIRST (direct asyncio.create_task)
         → Backend_Engineer creates MORE sub-tasks instead of writing code
         → Passive mode arrives later, but vLLM is busy with active requests
         → Result: infinite planning loop, zero code files
```

## Why It's Hard to Spot

- Both dispatches succeed (200 OK)
- Agent logs show `tool_executed: create_task` — looks productive
- No errors in logs
- Tasks are being created, phases advancing — appears to work
- The missing signal is the **absence** of `file_write` calls

## The Fix: Idempotent Claim + Deferred Active Delegation

### 1. Idempotent claim_task

The dispatcher pre-transitions tasks to `running` before the agent runs. When the agent calls `claim_task`, it fails with "already running". Fix: if task is running AND assigned to the calling agent, succeed silently.

```python
# In ClaimTaskTool.execute():
if task.status == TaskStatus.running and task.assigned_agent_id == ctx.agent_id:
    return f"Task '{task.title}' already claimed and running."
```

### 2. Defer active delegation for assigned agents

When the active-mode agent @mentions colleagues, check if they already have tasks assigned. If yes, skip active dispatch — let the GlobalDispatcher handle them in passive mode.

```python
# In _process_agent_in_background, delegation section:
agents_with_tasks = {query pending/running tasks with assigned_agent_id}
for delegate in delegated:
    if delegate.id in agents_with_tasks:
        logger.info("delegation_deferred_to_passive", agent=delegate.name)
        continue  # GlobalDispatcher will handle in passive mode
    asyncio.create_task(_process_agent_in_background(...))
```

### 3. DB session scope

The delegation check needs its own DB session — the setup session is already closed by the time delegation happens (after the potentially long LLM call).

```python
# WRONG: setup_db is already closed
result = await db.execute(...)  # NameError or stale session

# RIGHT: open a new short-lived session
async with async_session() as _deleg_db:
    result = await _deleg_db.execute(...)
```

## Design Tension

Blocking active delegation entirely breaks the natural workflow ("you can't ignore a colleague's request just because you're busy"). The compromise:

- **Managers without tasks** (CEO, CMO): always active — they plan and delegate
- **Workers with assigned tasks** (Backend_Engineer, Designer): deferred to passive — they execute
- After passive work completes, they can receive new active mentions

## Diagnostic Checklist

When agents produce plans/tasks but no artifacts:

1. Check `tool_executed` logs — are agents calling `create_task` or `file_write`?
2. Check `get_tools_for_mode` — does the agent's mode include execution tools?
3. Check for `claim_task` errors — "already running" means dispatcher pre-transitioned
4. Check for dual dispatch — same agent name in both `delegation_triggered` and `passive_agent_dispatched`
5. Check vLLM concurrency — many simultaneous active dispatches starve passive agents

## Related Patterns

- **asyncio.create_task silent failure**: Background tasks swallow exceptions unless you add `task.add_done_callback`. An error in delegation logic (e.g., NameError from wrong variable) produces zero log output.
- **vLLM sequential bottleneck**: With N agents dispatched simultaneously but only 1 GPU, active mode agents monopolize inference time. Passive agents queue behind them and may never reach execution within the test window.
