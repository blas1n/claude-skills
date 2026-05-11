---
name: acceptance-gate-must-measure-delta-not-state
description: When designing or reviewing an acceptance gate (M0 quality gate, CI pass/fail, deploy guard, eval harness), make the gate compare *change attributable to the work* against a baseline — not just the post-state. If a no-op execution can pass the gate using only pre-existing fixtures, the gate measures correlation, not causation, and the cheapest path to "pass" will be the no-op.
version: 1.0.0
task_types: [eval, quality, ci, gate-design]
triggers:
  - pattern: "designing an acceptance gate / quality gate / pass-fail criterion / eval harness scoring rule"
  - pattern: "writing an LLM-eval that scores by 'does the verifier pass?'"
  - pattern: "writing a strict_pass / fake_verified / hallucination guard"
  - pattern: "M0 / M1 / M2 measurement spec for BSNexus"
---

# Acceptance gate must measure *delta*, not *state*

A lesson from BSNexus G6.4 (2026-05-11), captured one merge cycle after the failure.

## The trap

G6.4 wired the M0 measurement bridge: `BenchmarkTask → dispatch_run_attempt → VerifierWorker → TaskTelemetry → AcceptanceReport`. Spec:

```python
fake_verified = telemetry.proof_state == ProofState.verified and not verifier_shaped_proof
strict_pass = (
    telemetry.proof_state == ProofState.verified
    and verifier_shaped_proof
    and not fake_verified
    and telemetry.deliverables_created > 0
)
```

`verifier_shaped_proof` was "command contains pytest/test/build and exit 0 and not setup-only". Looks tight.

First live run against qwen3-coder:30b on a seed workspace (a `pyproject.toml` + one `def test_seed_always_passes(): assert True`) produced:

```
strict_pass: 19/19
fake_verified: 0
greenfield_exit_ready: True
```

By the gate, ready for G8 (repo-native delivery automation). By reality, the LLM had emitted **rounds=0, tools=0** — text responses only, no file writes. The pre-existing passing test was re-run on an untouched tree. The gate happily declared "verified".

The spec checked *the verifier looks real* (correlation: pytest exit-0 usually means work happened). It never checked *the work actually happened* (causation: did the workspace change because of this run?).

## The fix in our case (G6.5)

Add a *delta* field to telemetry and re-derive `fake_verified` off it:

```python
@dataclass(frozen=True)
class TaskTelemetry:
    ...
    workspace_files_touched: int = 0   # NEW — bridge pre/post snapshot diff

def evaluate_task_result(task, telemetry):
    verifier_shaped_proof = _has_verifier_shaped_proof(telemetry)
    fake_verified = telemetry.proof_state == ProofState.verified and (
        not verifier_shaped_proof or telemetry.workspace_files_touched <= 0
    )
```

The bridge snapshots `workspace_root` *before* the LLM dispatch (mtime+size of every non-ignored file) and *before* the verifier runs (so the verifier's own side effects — `__pycache__`, `.pytest_cache` — don't pollute the count). Ignore set: `.git`, `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `.venv`, `node_modules`, `dist`, `build`, `*.pyc`.

Re-run flipped 19/19 strict_pass → 0/19 strict_pass + 19/19 fake_verified. The gate refused. Correct refusal.

After we then added the tool loop (G6.6), the *same* gate produced 2/19 real strict_pass + 14 fake_verified + 2 round_cap_blocked + 1 verification_missing. That's the actual M0 baseline signal — a number the next iteration can be measured against.

## The general pattern

This trap fires whenever **both** are true:

1. The gate scores by examining post-state artifacts (test exit code, build output, file existence, db row, deploy health probe).
2. A no-op execution can produce the same post-state, because pre-existing fixtures already satisfy the artifact check.

The cheapest path to passing the gate is then the no-op. **Goodhart's Law in 30 lines of Python.**

The fix is always the same shape:

- **Capture a pre-state baseline** before the work starts. State is whatever the gate eventually examines (filesystem, DB, deployed image hash, model weights, …).
- **Capture a post-state** after the work but before any verifier with its own side effects runs.
- **Score the delta**, not the post-state. Specifically: "did the post-state diverge from baseline in a direction attributable to the work?"
- **Add the delta as a separate telemetry field** so the failure mode "work didn't happen" is bucketed distinctly from "work happened but failed verification". These are different debugging paths and conflating them costs you weeks.

## Examples beyond M0

- **CI test gates**: "pytest passes" ≠ "tests pass *because of this PR*". Mutation testing / coverage delta makes the gate causal.
- **DB migration gates**: "migration applied without errors" ≠ "data has the new shape". Add `SELECT` invariants pre/post.
- **Deploy health gates**: "service responds 200" ≠ "the *new* image is serving". Check the running image digest matches the freshly built one.
- **LLM eval harnesses**: "the model gave a long answer" ≠ "the model solved the problem". Reference-solution diff / unit-test-pass-on-generated-code.
- **Code-review bots**: "linter passes" ≠ "the change adds value". Detect "comment-only" or "whitespace-only" diffs separately.

## Checklist when designing an acceptance gate

Before declaring the gate done, walk through:

1. **What does the post-state look like for a no-op execution?** If it could be indistinguishable from a real-work execution given the right fixtures, the gate is correlational.
2. **What artifact change is the work specifically supposed to produce?** Filesystem delta, DB row delta, deployed-digest change, generated-token-diff, …
3. **Can you compute that delta cheaply?** A pre/post snapshot in the harness usually costs <10ms — small enough to always include.
4. **Is the delta a distinct telemetry field or is it inferred from a composite?** Make it a separate field. Composite fields hide the failure mode.
5. **Is the ignore set documented?** Cache directories, build artifacts, etc. — they bias the delta upward. Pick the set explicitly and write it down so future contributors don't add another silent gap.
6. **Do you have a "no-op execution" test case in the harness suite?** Run the gate against a stub that does nothing and assert it *fails*. This single test catches future spec drift.

## Why this is worth a skill

The next time we (or another team in the BSVibe portfolio — BSage, BSupervisor, BSGateway, Bloasis backtester) design an acceptance gate, the same reasoning applies. The lesson is not "remember to snapshot files in the BSNexus M0 harness" — it's "every gate-design exercise needs the delta question asked explicitly". Capturing the pattern (not just the BSNexus instance) means the next gate doesn't ship as correlation-only.

## References

- BSNexus PR #110 (G6.4) — spec with the trap.
- BSNexus PR #111 (G6.5) — spec fix + 2026-05-11 first/second measurement reports archived in `backend/measurement/`.
- BSNexus G6.6 (this branch, post-merge will be PR #112) — first real signal once tool-loop + delta-aware spec compose.
