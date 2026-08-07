---
name: hook-prefix-matcher-skips-compound-command
description: A PreToolUse Bash hook that gates on a command PREFIX (`[[ "$COMMAND" != git\ commit* ]] && exit 0`) silently no-ops when you write a compound command like `git add -A && git commit …`. The action succeeds, the hook never ran, and you report "verification passed" when nothing was verified.
category: trap
---

# Hook prefix matcher skips compound commands

## Problem

A common Claude Code guard runs the test suite before a commit:

```bash
# ~/.claude/hooks/pre-commit-verify.sh
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""')
if [[ "$COMMAND" != git\ commit* ]]; then
  exit 0                       # not a commit — nothing to do
fi
...
uv run pytest "$TEST_DIR" || { echo "BLOCKED: Unit tests failed." >&2; exit 2; }
```

The matcher tests the **whole command string** against a prefix. So this fires:

```bash
git commit -m "..."                    # matches → suite runs → can BLOCK
```

and this does not:

```bash
git add -A && git commit -m "..."      # does NOT match → exit 0 → suite NEVER runs
```

Same for `cd repo && git commit …`, `git add . ; git commit …`, and anything
where `git commit` is not the leading token.

The failure is silent and *inverted*: the guard exists to stop you, so its
silence reads as approval. A commit that sails through feels verified. It isn't.

Observed cost: a broken test rode through two commits and was caught only by CI,
after the earlier attempt (`git commit` alone) had been correctly blocked —
which made the later "pass" look like the fix had worked.

## Detection

The hook's own output is the tell. A hook that ran prints its banner in the tool
result:

```
[pre-commit] Running pytest...
```

**No banner ⇒ the hook did not run.** Before claiming a hook verified anything,
look for its output. `git commit` succeeding is not evidence.

Confirm the matcher directly when unsure:

```bash
grep -n 'COMMAND' ~/.claude/hooks/<hook>.sh
```

## Solution

1. **Own the verification; don't delegate it to a hook.** Run the gate yourself
   and read the result, then commit:
   ```bash
   uv run pytest tests/ -q          # you see this pass
   git add -A
   git commit -F - <<'MSG'
   ...
   MSG
   ```

2. **If you want the hook to fire, keep the matched token first.** Stage in a
   separate call so the commit command starts with `git commit`:
   ```bash
   git add -A            # call 1
   git commit -F - ...   # call 2 — hook matches
   ```

3. **Never phrase a report as "the hook passed"** unless you saw its banner. Say
   what you actually ran.

4. **If you own the hook**, make the matcher substring-based and anchor on the
   real intent:
   ```bash
   if ! grep -qE '(^|[;&|]\s*)git\s+commit\b' <<<"$COMMAND"; then exit 0; fi
   ```

## Sibling failure: the hook runs but its tooling isn't installed

The inverse also bites. In a **fresh git worktree** the venv has no dev
dependencies, so the hook's `uv run pytest tests/` cannot spawn `pytest`,
exits non-zero, and reports:

```
BLOCKED: Unit tests failed. Fix before committing.
```

Nothing failed — nothing ran. Reproduce the hook's exact command before
believing its verdict:

```bash
uv run pytest tests/ -q          # → "error: Failed to spawn: `pytest`"
uv sync --extra dev              # then the hook's command works for real
```

Same lesson from the other direction: **a gate's verdict is only meaningful if
you know the gate executed the thing it claims to have executed.**

## Generalisation

Any guard keyed on surface form rather than effect has this hole — lint hooks
matching `^npm run build`, deploy guards matching `^kubectl apply`, audit hooks
matching `^psql`. The rule: **a silent guard is indistinguishable from a passing
guard, so require positive evidence that it ran.**

## Related

- `feedback_prompt_hooks_crash` — hook config shape (command type required)
- `verification-before-completion`
- `piped-gate-masks-exit-code` — the same "gate silently didn't gate" family
