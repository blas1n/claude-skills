---
name: boundary-test-must-not-supply-the-answer
description: "A boundary test that passes the value it expects back (acquire(id, '/founder/path') → assert mount == '/founder/path') is passed forever by an implementation that just echoes its argument — the real caller passes something else. Pair trap: a fail-closed 'absence' rung then swallows the resulting infra failure and reports it as an honest, unalarming verdict."
version: 1.0.0
task_types: [testing, debugging, design, review]
triggers:
  - pattern: "writing or reviewing a test for an adapter / manager / factory that takes a path, URL, id, or config and hands it to a collaborator"
  - pattern: "a subsystem is 100% green in CI but fails on the first real request / run in production"
  - pattern: "designing a fail-closed ladder with a 'not applicable' / 'nothing found' / 'no gate' terminal"
  - pattern: "a production run reports a benign absence ('no manifest', 'no changes', 'not configured') that you did not expect"
category: trap
---

# Boundary Tests Must Not Supply the Answer

## The Law

**The value you inject in a test is the value you fail to verify.**

A test that hands the unit the answer it then asserts on cannot distinguish a correct
implementation from `return arg`. Production is the only caller whose argument is real.

```python
# The test that proves nothing
box = await mgr.acquire(project_id, "/Users/founder/proj")
assert box.workspace_mount == "/Users/founder/proj"   # an echo passes this forever
```

Nothing here says the founder's path ever *reaches* `acquire`. It says the manager can
copy a string.

```python
# The test that proves something — pass what the REAL caller passes
box = await mgr.acquire(project_id, f"/app/var/runs/{uuid4()}")   # agent_loop's actual arg
assert box.workspace_mount == "/Users/founder/proj"               # config must win
```

## Why It Keeps Happening

The trap is invisible because the test *looks* like it exercises the contract. Three
conditions make it lethal:

1. The unit takes a value that **looks like** what it should use.
2. The real caller supplies a **different** value from a different layer.
3. Nothing in the test suite ever plays the real caller.

Corollary — **a parameter that is always empty or always constant in production is not an
input, it is a lie**. If every production call site passes `[]`, the call is asserting
something ("nothing changed") when the truth is different ("this side cannot see").

## Real Example — BSVibe #692 in-place verify (2026-08-09)

Two production defects shipped 100% green, back to back, from the same disease. Both were
found only by running the feature end-to-end in production three times.

### #716 — the manager echoed the caller's path

`ClientWorkerSandboxManager.acquire(project_id, workspace_path)` used its argument.
The real caller, `agent_loop`, passes the run's **server-side** directory
(`/app/var/runs/<run_id>`) — a path that does not exist on the founder's machine, which is
where this box executes.

Result: every gate command failed with `client_attach_workspace_missing`; no manifest could
be read; the run settled `UNTESTED`.

Fix: WHERE a run executes is **dispatch context** (it comes from the product), so the
**manager owns it** and ignores the caller's per-run path.

### #717 — the call asserted "nothing changed"

`run_inplace_gate` passed `written_paths=[]` to the gate deriver, which rendered as
`Files changed by this work step: (no files changed)`. The deriver answered
`applicable=false` — nothing to verify.

But `written_paths` is **always** empty for this execution model: the agent uses the CLI's
native tools, so the server observes no writes. "The server cannot see what changed" is not
"nothing changed", and the deriver reasoned from the falsehood.

Fix: ask the machine that *can* see. Capture `git rev-parse HEAD` **before** the loop (the
agent's own commits move HEAD afterwards), then union `git status --porcelain` with
`git diff --name-only <baseline>..HEAD`. Only filenames cross the wire, so a
source-privacy contract survives.

## The Pair Trap: fail-closed absence rungs swallow infra failures

Both defects were *silent* — no alarm, no false claim. A fail-closed honesty ladder had
been designed exactly right:

| rung | verdict |
|---|---|
| no manifest on that machine | genuinely gateless → `None`, stays UNTESTED |
| deriver could not run | `passed=False`, never proved |
| command ran and failed | honest failure |
| command ran and passed | PROVED |

The ladder **never produced a false proof**. But the top rung is an *absence sink*: an
unreachable machine and a repo with no build config both produce zero manifests. The wiring
break drained into the absence rung and **wore its legitimacy** — the system reported
"this repo has no gate", which is a perfectly reasonable thing to hear.

> A fail-closed design converts wiring failures into *credible* verdicts. It protects
> correctness and destroys the alarm.

**Defense — make absence prove itself.** Before concluding "there is none", probe that you
could have seen one:

```python
try:
    await box.list_dir(".")            # can I reach this workspace at all?
except SandboxError:
    return fail_closed("probe_failed")  # infra failure — NOT "no gate here"
manifests = await read_manifests(box)
return None if not manifests else ...   # only now is absence real
```

And never swallow a probe error silently — `ruff S112` flags `try/except/continue` for
exactly this reason. Log it: an unlogged probe failure reads downstream as a fact.

## Checklist

When writing or reviewing a boundary test:

- [ ] Does the test pass the value it later asserts on? → rewrite it to pass the **real
      caller's** value and assert the configured one wins.
- [ ] Would `return arg` / `return []` pass this test? → the test is an echo check.
- [ ] Grep the production call sites. What do they *actually* pass? Is any parameter always
      empty or constant? → it is config, not input, and the call may be asserting a falsehood.
- [ ] Does any code path terminate in "not applicable / none found / not configured"?
      → add a probe that separates infra failure from real absence, and log the failure.
- [ ] Has the feature run end-to-end in production? Unit-green is not prod-works — both
      defects above survived a full suite and died on the first real run.

## Related

- `mock-fixtures-hide-wiring-bugs` — dependency overrides + pre-seeded fixtures hiding glue
- `absence-measurement-validity-check` — before concluding "X = 0", check the producer runs
- `capability-guard-must-assert-presence` — guards that check only for the forbidden miss zero-capability
- `half-wired-subsystem-audit` — the visible half ships, the invisible half never gets wired
