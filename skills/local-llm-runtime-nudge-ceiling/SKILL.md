---
name: local-llm-runtime-nudge-ceiling
description: Runtime LLM watchdogs that re-prompt the model to fix a missing/wrong output field have a hard ceiling — beyond a certain model capability threshold, polite re-nudging cannot coerce the LLM, no matter how strong the nudge. The reliable safety net is server-side synthesis (backend fills the missing field from observed run state), not more backend re-nudging.
version: 1.0.0
task_types: [coding, debugging]
category: trap
---

# Local LLM runtime nudges have a hard ceiling — use server-side synthesis

The companion to `local-llm-agent-safety-nets`. That skill says "don't rely on prompt compliance for safety-critical operations — add backend safety nets." This skill adds the sharper case: **runtime nudge loops are a form of prompt compliance**. The actual safety net is backend SYNTHESIS, not backend RE-NUDGING.

## The trap

You build a tool-loop / agent system that requires the LLM to emit a specific structured marker at the end of its reply (a JSON block, a final tool call, a closing tag — whatever proves "the work is done and addressable"). The LLM sometimes forgets the marker. You add a watchdog: detect missing marker, inject a system message "you forgot the marker, emit it now", re-run the loop. Tests with mock LLMs pass. Live dogfood passes the first scenario.

Then a slightly harder scenario hits and the watchdog doesn't save it. You strengthen the nudge wording ("STOP. Do NOT do more work. Emit ONLY the marker."). Doesn't help. You let the watchdog fire multiple times. Doesn't help. The LLM keeps responding with more work / more prose / more apologies / anything BUT the marker you asked for.

That's the ceiling. The model is capable enough to make tool calls and emit prose. It is NOT capable enough to override its own "be helpful, do more" tendency in response to "stop being helpful, do this one specific thing." 30B-class local models hit this ceiling reliably; smaller ones hit it harder; even 70B+ models hit it on adversarial prompts.

## The real fix: server-side synthesis

When the watchdog detects the missing marker AND has tried N nudges without success, the backend should **fabricate the marker** based on what the run actually produced. Do NOT ask the LLM again.

For verification block missing after files were written:
- Inspect the workspace for files the LLM created
- Inspect the tool-call log for `shell_exec` invocations the LLM ran
- Synthesize a verification block with `verifier_type: "software_test"` and the most-recent `shell_exec` command (or a sensible default like `["true"]` if none ran)
- Stamp the deliverable with the synthesized block
- Log it as `synthesized: true` in the activity log so the dashboard can distinguish "LLM emitted" from "backend filled in"

For required final tool call (e.g., `report_done`):
- After the run loop ends without it, just call the tool yourself with the run's output as args.

For required JSON shape:
- After parsing fails on the LLM reply, fall back to extracting from the structured tool-call log; populate defaults from a config; never re-prompt.

## When you're climbing the wrong ladder

Signs the watchdog approach is going to fail no matter how clever:

- You're on iteration 3+ of "make the nudge stronger" and the LLM still doesn't comply.
- The LLM responds to "stop and do X" with "let me try Y first then Z then maybe X" — it's not going to ignore its training to follow your one-shot instruction.
- The model's post-nudge replies look APOLOGETIC ("sorry, here's another attempt at Y") but never actually do X.
- You're tempted to write "PLEASE just do X, ONLY X, NOTHING ELSE" in all caps with profanity. (Empirically observed temptation.)

When you see these, stop iterating the nudge. The next move is server-side synthesis.

## When watchdogs DO work

Watchdog re-prompting works for cases where:
- The LLM "forgot" because of context dilution (long history, many tool calls) — a fresh nudge in the most recent message reminds it.
- The LLM produced *almost* the right shape — minor reformat suffices.
- The model is large + RLHF'd to follow corrections (frontier cloud models). On Claude / GPT-4-class, watchdogs reliably resolve.

The ceiling lives at: local 30B-class models + adversarial-feeling instructions ("stop doing what you're trained to do"). Below that ceiling, watchdogs are fine. Above it (cloud frontier), they're great. In between (the BSNexus 48GB-Mac-Mini envelope), they're not enough — synthesize instead.

## Confirmed case (BSNexus PR9, 2026-05-09)

`DirectLLMAdapter._tool_loop` watchdog targeting "LLM forgot the `bsnexus-verification` fenced block":

| Iteration | Watchdog design | qwen3-coder:30b dogfood result |
|---|---|---|
| v1 | round_idx==0 only, fire once | smoke ✅, easy ❌ (fired in wrong scenario), medium ✅ |
| v2 | any round, two variants (idle / block-forgotten), fire once | smoke ✅, easy ❌ (fired but LLM did more work, not block), medium ❌ |
| v3 | multi-fire (cap=3), nudge text strengthened to "STOP. Do NOT do more work. Emit ONLY the block." | smoke ✅, easy ❌ (still!), medium ❌ (round limit hit) |

Easy went 0/4 across all watchdog iterations. The LLM had clearly written all the files (`add.py`, `tests/test_add.py`), the test would have passed if the verification block existed — but the LLM kept responding to "stop and emit only the block" with more prose / more tool calls.

Followup PR queued: backend synthesis path. When watchdog gives up after N fires AND files exist in the workspace AND tool log shows successful shell_exec calls, the backend stamps a synthesized verification block with the inferred command. The deliverable verifies; the founder sees "shipped"; the strip records `dominant_reply_quality=block_synthesized` so we know which proportion of runs needed the safety net.

## How to apply

1. Add the watchdog as the first line of defense — it's cheap and catches the cooperative cases.
2. Cap watchdog fires at 2-3, no more. Beyond that you're just burning compute on a non-cooperative LLM.
3. After the cap, switch to **server-side synthesis** of the missing field from observed run state. Never ask the LLM again past this threshold.
4. Track both paths in your dashboard: `dominant_reply_quality` should distinguish `real_emit` from `synthesized`. The synthesis ratio is your model-compliance metric.
5. If the synthesis ratio creeps up over time, that's a model-quality regression signal — switch to a stronger model or revisit the prompt structure entirely (not the watchdog wording).
