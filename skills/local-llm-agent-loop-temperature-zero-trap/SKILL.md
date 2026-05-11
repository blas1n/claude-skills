---
name: local-llm-agent-loop-temperature-zero-trap
description: "Setting `temperature=0` for a tool-calling agent loop on a smaller local LLM (qwen3-coder:30b, Llama-3 30B-class, glm-4.7-flash 29.9B etc.) tightens variance BUT cuts mean accuracy hard — sometimes 5–10×. Greedy decoding locks the model into a wrong first-token path that subsequent rounds can't escape. The same sampling that creates run-to-run noise is also what gives the loop room to self-correct."
version: 1.0.0
task_types: [eval, llm-tooling, agent-design]
triggers:
  - pattern: "deciding whether to set temperature=0 for an agent loop / tool-calling pipeline / eval harness"
  - pattern: "measuring run-to-run variance on a multi-turn LLM workflow and proposing 'just set temperature=0'"
  - pattern: "designing reproducibility controls for an M0/M1 quality gate"
  - pattern: "any 'reduce noise by going greedy' suggestion on a local <50B model in an agent context"
---

# Local-LLM agent loops: temperature=0 cuts mean while tightening variance

A negative result from BSNexus G6.8 (2026-05-11) — the *expected* shape was "fewer wins per run, same mean across runs". The actual shape was "near-zero variance, *much* lower mean".

## The measurement

Same prompt, same workspace, same model (qwen3-coder:30b via Ollama), same 19-task suite, same tool registry (file_read / file_list / file_write / shell_exec), N=3 each:

| metric                    | default temp | temperature=0.0 |
|---------------------------|-------------:|----------------:|
| total strict_pass cells   |  7/57 (12.3%) |  1/57 (1.7%)   |
| per-run strict_pass mean  |  2.33 / 19   |  0.33 / 19      |
| per-run strict_pass stdev |  2.05        |  0.47           |
| total fake_verified cells |  8           |  2              |
| dominant failure mode     |  mixed       |  `verification_failed` |

`verification_failed` means: LLM wrote files, verifier ran, exit ≠ 0 — i.e., real-but-broken code. Under greedy decoding the model attempted more tasks (rounds=0 cases went down to single digits) but the code it produced was structurally wrong in a way the verifier caught every time.

## Why this happens

Two compounding factors:

1. **Tool-loop path lock-in.** In a multi-turn agent loop the *first* token of each turn picks a strategy: which file to read first, which path to write, which shell command to run. Greedy decoding commits to whichever strategy has the highest single-token probability — which on a small model is often a near-tie between several reasonable approaches. Sampling sometimes picks the right one; greedy picks one approach and rides it to the bottom.

2. **No self-correction headroom on smaller models.** Larger models (70B+, frontier API models) have enough representational margin to notice "I'm on the wrong path" and switch even under greedy. ≤30B local models don't — once the loop is in a bad branch, every subsequent turn reinforces it because the input context now contains the wrong path's history. Sampling lets the next turn re-roll the strategy; greedy doesn't.

Folklore "use temperature=0 for code generation" comes from **single-turn completions** (autocomplete, IDE assist) where the path is short enough that one wrong token = one bad output. In an agent loop, one wrong token at turn 1 = N bad turns at turns 2–N. Different regime.

## Decision rule

When you reach for `temperature=0` on a local model in an agent context, ask:

- **Single-turn structured output?** (JSON extraction, classification, fill-in-the-blank) → `temperature=0` is fine, often correct.
- **Single-turn freeform code?** → Mild lowering (0.2–0.4) is fine. Pure 0 may regress slightly on local models, negligible on frontier.
- **Multi-turn agent loop with tool calls?** → **Default to sampling** (provider default, usually 0.7–1.0). Lower only if you've measured that the model in question doesn't suffer the path-lock effect.

For evaluation harnesses specifically: **don't trade mean accuracy for variance reduction**. Run more samples instead — the right answer to "results are noisy" is K=3 or K=5 multi-run aggregation, not temperature=0. Multi-run aggregation reports stable signal *and* preserves the mean accuracy that sampling buys you.

## Detection: are you about to fall into this?

Symptoms before you have measurement data:

- "Let me set temperature=0 so the eval is reproducible" → reproducible *and lower*.
- "We need determinism for the M0 gate" → confusion between "the measurement is reproducible" and "the model is deterministic". Multi-run aggregation gives the former without sacrificing the latter.
- "But OpenAI cookbook says temperature=0 for code" → cookbook is single-turn. Verify the regime before transferring.

Cheap probe: run the same prompt 3× at default temp and 3× at temperature=0 on your actual workflow (not a toy task) and compare means. If mean drops more than ~10%, abandon `temperature=0`.

## What to do instead

To make a noisy gate reliable:

1. **Multi-run aggregation.** K=3 or K=5, per-task strict_pass rate, gate on rate ≥ threshold across runs (not per single run). BSNexus G6.7 wired this — see `quality.m0.MultiRunReport` + `aggregate_runs()`.
2. **Fixed seeds where the provider supports them.** Ollama's `/api/generate` accepts a `seed` parameter; LiteLLM forwards `seed=` for compliant providers. Combined with default temperature, you get *reproducible noise* — same random walk, different prompts produce comparable results.
3. **Per-task seed fixtures.** Reduce variance at the *task* level by making each benchmark task have a concrete starting state (failing test + half-written code), so the loop doesn't have to invent everything from scratch each turn. Less surface area for sampling to misroute.

## References

- BSNexus PR #115 (G6.8) — the experimental run + archived measurement under `~/Docs/BSNexus/measurement/m0_2026-05-11_g6_8_temp0.json`.
- BSNexus PR #114 (G6.7) — multi-run aggregation spec the right answer to noise-without-determinism.
- Sibling skill `acceptance-gate-must-measure-delta-not-state` (G6.5) — the broader pattern of measurement-spec evolution.
