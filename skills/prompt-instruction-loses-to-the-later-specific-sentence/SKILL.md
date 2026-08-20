---
name: prompt-instruction-loses-to-the-later-specific-sentence
description: Adding a rule to an LLM system prompt silently loses to a LATER, more specific sentence that covers the same case — including the "escape hatch" that lets the model opt out. Fix the sentence that actually fires, never stack emphasis in front of it. Unit tests that assert the new wording is PRESENT pass while the prompt never fires.
version: 1.0.0
task_types: [coding, debugging, design]
triggers:
  - pattern: "added an instruction to a system prompt and the model still doesn't do it"
  - pattern: "strengthening / emphasising prompt wording had no effect"
  - pattern: "prompt has an 'if not applicable, return nothing / set applicable=false' escape"
  - pattern: "prompt unit tests pass but live behaviour unchanged"
  - pattern: "agent ignores a prohibition that was appended after its role definition"
category: trap
---

# A prompt instruction loses to the later, more specific sentence

## The trap

A system prompt misbehaves in one case. The obvious move is to **add a paragraph** covering that case. You add it, unit-test that the wording is in the prompt, ship — and live behaviour does not change at all.

The reason is not emphasis. It is that **somewhere else in the same prompt there is a sentence that matches the model's situation more specifically**, and specificity wins. The two most common shapes:

1. **An identity line at the top.** `"You are an autonomous engineer … use the tools to change files"` beats a later `"do not write any files"`. The model is not being lazy; it was told what it *is* before it was told what not to do.
2. **An escape hatch at the bottom.** `"If the change is not something a command can verify, set applicable=false and return nothing"` beats an earlier `"every stated constraint must become a check"` — because in exactly the case you care about (nothing was produced), the escape hatch is the more specific match.

Shape 2 is the nastier one: the escape hatch usually *reads* as reasonable, and it fires precisely in the situation your new rule was written for.

## Measured evidence (BSVibe, 2026-08-19 → 08-20)

Same instruction, three deployments, identical task input:

| Prompt | Result |
|---|---|
| Base only (tools withheld) | 0 tool calls — the agent **guessed** |
| Base identity + **appended prohibition** | 89 tool calls, **4 files edited and committed** — prohibition ignored |
| Identity **replaced** | 97 tool calls, **0 writes** (tree byte-identical) |

Then the same mistake in the other direction, on a different prompt:

| Prompt | derived checks from a stated constraint |
|---|---|
| Constraint paragraph **added before** the escape hatch | `applicable:false, commands:[]` — **0 checks** |
| Escape hatch itself made constraint-aware | constraint ×1 → **3 checks**; constraint ×2 → **2 checks, 1:1** |

The fix in both cases was the same shape: **edit the sentence that won, do not add another in front of it.**

## Solution

1. **Find the sentence that actually fired.** Read the prompt as the model in that exact situation: which single sentence most specifically describes "what I am looking at right now"? That is your edit target.
2. **Put the exception INSIDE that sentence**, and make it say why:
   - bad: add `"CONSTRAINTS: every constraint must become a check"` before the escape
   - good: `"If the change is not something a command can verify AND the intent states no constraint, set applicable=false … A stated constraint is checkable even when the work produced nothing to run: 'produced no output' is not the same as 'has nothing to prove'."`
3. **If the winner is an identity line, replace the identity** rather than appending a prohibition. And **delete the old wiring** — leaving two prompt sites that say different things to one run reproduces the failure.
4. **Teach the shape, not a list**, when the domain is unbounded (natural-language constraints, user intents). Hardcoding case-by-case never converges; the general mechanism usually already receives the input it needs.

## Test the POSITION, not the presence

This is the half that makes the fix stick. A test like:

```python
assert "constraint" in system_prompt.lower()   # ❌ passes for the broken version
```

passes for the very version that failed in production — the paragraph *was* there. Assert that the exception lives on the winning side of the sentence that beat it:

```python
head, _, tail = system_prompt.partition('set "applicable" to false')
assert tail, "escape-hatch sentence not found — this pin needs updating"
assert "constraint" in tail.lower(), (
    "the escape must itself state that a stated constraint keeps the gate applicable; "
    "a paragraph placed BEFORE it is overridden"
)
```

Now "just add another paragraph in front" cannot make the suite green.

## Key insights

- **Specificity beats order and beats emphasis.** More CAPS, more "MUST", more repetition do not move a model that has a better-matching sentence available.
- **An escape hatch is a rule too.** Every `if none/not applicable/skip` clause is a competing instruction — audit it whenever you add a rule that could fire in the same situation.
- **String-presence tests are alibis.** They certify the edit, not the behaviour. Prompt changes are only verified by a real run.
- **Two prompt sites saying different things = the same bug returns.** Fixing means replacing, not coexisting.

## Red flags

- "I added the instruction, let me make it stronger / add caps / repeat it."
- The prompt contains both a general rule and a narrower `if X, do nothing` clause.
- Prompt tests only do `assert "<word>" in prompt`.
- Behaviour is unchanged across two deploys of prompt edits.
- A prohibition appended after a role/identity sentence ("You are a …").

## 관련

- `local-llm-runtime-nudge-ceiling` — re-nudging at RUNTIME has the same futility; the fix there is server-side synthesis
- `local-llm-agent-safety-nets` — don't rely on prompt compliance for safety-critical operations
- `absence-measurement-validity-check` — before calling a prompt change "failed", confirm the path even runs
