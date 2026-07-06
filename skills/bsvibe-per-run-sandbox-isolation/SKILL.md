---
name: bsvibe-per-run-sandbox-isolation
description: BSVibe verification runs in a fresh /work clone of main for EVERY turn — files from failed prior turns are gone. Commit within the CURRENT turn or they vanish.
version: 1.0.0
task_types: [devops, debugging]
triggers:
  - pattern: working in a BSVibe task and verification keeps failing with missing module or file not found
  - pattern: verification sandbox cannot find files that were created in a previous turn
---

# BSVibe Per-Run Sandbox Isolation Trap

## The Trap

BSVibes verification sandbox at /work is a fresh clone of main for every verification attempt.
If verification fails, BSVibe abandons the per-run branch -- it is never merged.
The next turn starts again from main with zero trace of your previous work.

This creates a deceptive failure loop:
1. Turn 1: Write files, commit, declare contract -> verification fails (unrelated reason)
2. Turn 2: BSVibe re-invokes from clean main -- your files are GONE
3. You assume files from Turn 1 are present and only fix the unrelated reason
4. Verification fails again because the files still do not exist

Error looks like: ModuleNotFoundError: No module named src.my_module
even though you committed it last turn.

## Key Facts

- BSVibe captures: files in git status (working tree) OR commits on top of FETCH_HEAD within the CURRENT session/turn only
- Successful verification -> per-run branch is merged to main
- Failed verification -> branch is abandoned; next turn starts from main
- HEAD is always detached at FETCH_HEAD (last main commit)

## Diagnosis

**ALWAYS start a new turn with this before writing any code:**

  git log --oneline -5        # what is on main right now?
  ls src/ && ls tests/        # which files actually exist?

Do NOT rely on conversation history to know what files exist. The filesystem
is the ground truth. Check it first, then decide what to write.

  ls src/my_new_file.py tests/test_my_new_file.py   # do the target files exist?
  git log --oneline HEAD~3..HEAD                     # commits this turn?
  git status                                         # working tree changes?

If files do not exist -- you are in a fresh turn and must re-create them.

## Fix Protocol

Every turn is a fresh start. Do ALL of this within the SAME turn:

  0. Check filesystem first: git log --oneline -5 && ls src/ && ls tests/
  1. Write files (Edit/Write tool -- actually CALL the tool, do not narrate it)
  2. Verify locally: uv run ruff check + uv run pytest -v
  3. Fix any errors (pre-commit hook failures, test failures, lint)
  4. git add <files> && git commit -m ...
  5. git show --stat HEAD   # confirm BOTH src/ AND tests/ files appear
  6. THEN declare the verification contract

Step 5 is critical: if only tests/... appears in git show --stat but not src/...,
the implementation was described but never actually written. Re-write and re-commit.

BSVibe also captures uncommitted working-tree changes (git status), but committing
makes verification explicit and avoids ambiguity.

## Pre-Commit Hook Side-Trap

This project has a pre-commit hook that runs the FULL test suite before every commit.
Pre-existing environment failures (missing packages not installed locally) will block
your commit even though your code is correct.

Diagnosis:
  uv run pytest tests/ --tb=short -q 2>&1 | grep ModuleNotFoundError

Fix:
  uv pip install <missing-package>   # explicit install; uv sync may use stale lock
  uv run pytest tests/ 2>&1 | tail -3   # confirm all pass before committing

## Diagnostic Signal: Shifting Import Error Line Number

When the same verification failure repeats across turns but the error line number changes:

  # Turn 1: tests/test_event_bus_bsvibe.py:6  in <module>
  # Turn 2: tests/test_event_bus_bsvibe.py:3  in <module>
  # Turn 3: tests/test_event_bus_bsvibe.py:7  in <module>

This means the TEST FILE was committed each turn (pytest collected it, then failed on
import), but the IMPLEMENTATION FILE was never committed (src/ module missing from /work).
The AI re-created the test file with slightly different header structure each turn,
shifting the import line number, while the src file was described as written but
never actually captured in git.

Immediate fix:
  git show --stat HEAD   # check which files are actually in the commit

If only tests/... appears but not src/..., the implementation was never staged.
Re-write, stage explicitly, and commit again.

## Error Message Variant: "No module named 'src'"

BSVibe may report the truncated form:
  ModuleNotFoundError: No module named 'src'

even when src/__init__.py exists and other src.* imports work. This still means
the specific file (src/my_new_module.py) is absent from the clone -- the src
package itself is not broken, just the new file is missing.

## The Key Invariant

Every declared verification contract assumes its checked files exist in /work (BSVibes sandbox).
The only way they get there is if they were captured in THIS turns git diff or commits.
Never assume files from a prior failed turn are present.
Always write, verify locally, commit, and THEN declare.

## Verification Contract: `--extra dev` Is Not Portable

### The Trap

Even when your local pyproject.toml defines:

  [project.optional-dependencies]
  dev = ["pytest>=8.2.0", "pytest-cov>=5.0.0", "ruff>=0.5.0"]

The BSVibe verification sandbox rejects `uv run --extra dev` with:

  error: Extra `dev` is not defined in the project's `optional-dependencies` table

The sandbox resolves pyproject.toml from its own environment root — different uv
version, workspace layout, or policy blocks extras. ruff still passes (PATH tool),
but pytest-cov is unavailable.

### Symptom

Contract exits code 2 ("Extra `X` is not defined") while ruff exits 0.
Files exist; only the test runner is broken.

### Fix: Use `--with` Instead of `--extra`

  # Fragile — extras may not be honoured in sandbox
  uv run --extra dev pytest tests/test_foo.py --cov=src.foo --cov-fail-under=80

  # Portable — installs inline, bypasses pyproject.toml extras entirely
  uv run --with pytest --with pytest-cov pytest tests/test_foo.py --cov=src.foo --cov-fail-under=80 -q

### Standard Portable Contract Template

  {"checks": [{"kind": "command", "command":
    "uv run ruff check src/my_module.py tests/test_my_module.py && uv run --with pytest --with pytest-cov pytest tests/test_my_module.py --cov=src.my_module --cov-fail-under=80 -q"
  }]}

Rule: Never use `--extra <name>` in BSVibe verification contracts. Always use `--with <pkg>`.

## Diagnostic Signal: `derived_gate PASSED` but `outcome_demonstration FAILED`

### The Trap

The verification JSON contains TWO distinct result sections run in DIFFERENT sandboxes:

  "derived_gate": {"passed": true, ...}   <- contract command ran in AGENT's sandbox
  "outcome_demonstration": {"verdict": "failed", ...}  <- probe ran in FRESH CLONE

When `derived_gate.passed: true` but `outcome_demonstration.verdict: "failed"`:
- The ruff/pytest contract commands ran in the agent's working directory (files exist there)
- BSVibe's outcome probes ran in a SEPARATE fresh clone of main (files not there)
- Root cause: files were created with Write/Edit tools but NOT committed to git

### Why This Is Deceptive

The contract command `uv run pytest tests/test_lists.py` passes because pytest runs
against the agent's local files. Then BSVibe additionally runs outcome_demonstration
probes (e.g. `cd /bsvibe-task-XXXXX && uv run python -c "from toolkit.lists import chunk"`).
That cd path is a completely different directory -- a fresh clone where only committed
changes appear.

  Failure loop:
  Turn 1: Write file, declare contract -> derived_gate PASSES, outcome_demo FAILS
  Turn 2: Same files written (not committed) -> same failure
  Turn 3: Write + git commit -> BOTH pass

### Diagnostic Check

Look at the `outcome_demonstration.probes[].command` in the failure JSON.
The `cd /bsvibe-task-XXXXXX` path is a DIFFERENT directory from your working directory.
If these differ -> your files must be in a git commit to appear there.

  # My working dir:         /bsvibe-task-7a5daagc/
  # Outcome probe ran in:   /bsvibe-task-g03pztyz/   <- DIFFERENT
  # Fix: git add + git commit before declaring contract

### Rule

"Contract command passes locally" does NOT mean BSVibe outcome probes will find the files.
Always commit before declaring the contract -- the commit is what bridges the two sandboxes.
