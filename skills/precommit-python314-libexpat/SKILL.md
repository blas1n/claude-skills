---
name: precommit-python314-libexpat
description: "pre-commit fails to create hook env when host has python 3.14 — pyexpat ABI mismatch with macOS system libexpat. Pin language_version + provide python3.11 on PATH."
version: 1.0.0
triggers:
  - pattern: "pre-commit hook install fails on macOS with `Symbol not found: _XML_SetAllocTrackerActivationThreshold` or any pyexpat dlopen error"
---

# Pre-commit + Python 3.14 / libexpat ABI mismatch on macOS

## Symptom

`git commit` runs the pre-commit hook, which tries to build its
isolated env, and dies during virtualenv bootstrap:

```
[INFO] Installing environment for https://github.com/pre-commit/pre-commit-hooks.
An unexpected error has occurred: CalledProcessError: command:
('/opt/homebrew/Cellar/pre-commit/.../python', '-mvirtualenv',
 '/Users/.../py_env-python3.14')
return code: 1
stdout:
    ImportError: dlopen(/opt/homebrew/Cellar/python@3.14/3.14.4_1/.../pyexpat.cpython-314-darwin.so):
      Symbol not found: _XML_SetAllocTrackerActivationThreshold
      Referenced from: pyexpat.cpython-314-darwin.so
      Expected in: /usr/lib/libexpat.1.dylib
```

## Why

- pre-commit picks the highest-version Python it can find on PATH for
  `language: python` hooks (or whatever the system points at).
- Homebrew's `python@3.14` was compiled against a newer `libexpat`
  than what macOS Sequoia ships at `/usr/lib/libexpat.1.dylib`.
- The new symbol `_XML_SetAllocTrackerActivationThreshold` doesn't
  exist in the system lib → pyexpat's `.so` fails to dlopen → any
  Python 3.14 import that touches pyexpat (including `virtualenv`)
  crashes immediately.

This is **not** a hook misconfiguration; the host Python is broken.

## Diagnosis (one-liner)

```bash
python3.14 -c "import pyexpat" 2>&1 | head -3
```

If this prints `Symbol not found: _XML_SetAllocTrackerActivationThreshold`,
the host Python is the culprit. Confirm 3.13 still works:

```bash
python3.13 -c "import pyexpat; print('ok')"
```

## Fix

Two pieces — pin the hook's Python version, then make sure that
version is available on PATH.

### 1. Pin `default_language_version` in `.pre-commit-config.yaml`

Match whatever the project's runtime targets (devcontainer
Dockerfile, `pyproject.toml requires-python`, etc.):

```yaml
# Pin to project's Python (matches .devcontainer/Dockerfile + pyproject)
# Avoids host-default 3.14 picking, which has the libexpat ABI issue.
default_language_version:
  python: python3.11

repos:
  - repo: ...
```

This is a committed change — it benefits every contributor who
might hit the same trap, not just you.

### 2. Provide `python3.11` (or pinned version) on PATH

If the host doesn't have it, options in order of invasiveness:

**Symlink uv-managed Python** (least invasive, no brew install):

```bash
ls ~/.local/share/uv/python/  # find a cpython-3.11.* dir
ln -s ~/.local/share/uv/python/cpython-3.11.14-macos-aarch64-none/bin/python3.11 \
      /opt/homebrew/bin/python3.11
python3.11 -c "import pyexpat; print('ok')"  # verify
```

**Or `brew install python@3.11`** — heavier, but standard.

## Why not pin to `python3` or skip with `--no-verify`

- `python3` resolves to whatever's first on PATH — same broken 3.14.
- `--no-verify` skips real lint/format checks too, not just the
  bootstrap. Hides actual code issues. Don't use without an explicit
  user-OK for the specific commit.

## Sanity check

After fixing, the next `git commit` should bootstrap once and then
silently re-use the cached env on every subsequent commit:

```
trim trailing whitespace.................................................Passed
ruff (legacy alias)......................................................Passed
ruff format..............................................................Passed
[branch hash] commit message
```

## When this can happen elsewhere

Any tool that creates a Python virtualenv from the host interpreter
will hit it the same way: tox, nox, even some IDE test runners.
The fix is identical — pin the Python version the tool uses.
