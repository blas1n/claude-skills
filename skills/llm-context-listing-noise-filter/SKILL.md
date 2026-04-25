---
name: llm-context-listing-noise-filter
description: When directory listings feed an LLM prompt with a truncation cap, filter package-manager and build dirs FIRST or the cap silently buries the actual signal under noise. Recurring AI-engineering trap.
---

# LLM Context Listing Noise Filter

When you pass a directory listing into an LLM prompt — for "what files
already exist?" / "what was just shipped?" / "what's the current
project state?" questions — you almost always need to truncate. And the
moment you truncate, **noise dirs become an active threat to the
signal**, not just clutter.

## The exact failure mode

A replanner LLM was supposed to apply rule "no duplicate work":

```
Before you commit to a phase_direction, list (mentally) what files it
would create. Then check workspace_files and history[].files_written.
If your phase would mostly recreate paths that are already there,
pivot to the NEXT step.
```

Test 1: founder's intent decomposed correctly into [backend, frontend,
deployment]. Phase 1 ran "Backend Setup", wrote `package.json`,
`server.js`, `test.js`. Phase 2 the replanner picked **"Backend Setup"
again** — identical phase_name, identical directive, byte-for-byte.

The prompt was right. The model wasn't rebellious. The signal was
poisoned: `workspace_files` was a 200-entry list, sliced from a sorted
rglob, and `node_modules/@noble/hashes/...` filled all 200 slots.
`server.js` was on the cutting-room floor. The model saw "no backend
shipped" and picked Backend Setup.

```python
# What the model received (truncated to first 200 of 5000+ entries):
workspace_files = [
    "node_modules/.bin/mime",
    "node_modules/.bin/semver",
    "node_modules/@noble/hashes/_assert.d.ts",
    "node_modules/@noble/hashes/_assert.d.ts.map",
    # … 196 more node_modules entries
]
# What was actually on disk: also package.json, server.js, test.js
```

## The lesson

**Filter noise BEFORE truncating, not after.** Sorting is not enough;
caps are not enough; passing more context is not the answer. The
filter is the answer, because it changes the *signal-to-noise ratio at
truncation time*, not just the truncation point.

```python
# Wrong: filter after truncation
files = list_all_files(project_id)[:200]  # already too late
files = [f for f in files if not is_noise(f)]

# Wrong: rely on sort order to bury noise
files = sorted(list_all_files(project_id))[:200]  # still loses signal

# Right: filter inside the listing function, by default, before any cap
def list_files(project_id, *, include_noise=False):
    for entry in rglob(...):
        rel = entry.relative_to(root).as_posix()
        if not include_noise and rel.startswith(NOISE_PREFIXES):
            continue
        yield entry
```

## What to filter

```python
NOISE_PREFIXES = (
    # JS / Node ecosystem
    "node_modules/", ".pnpm-store/", ".yarn/",
    # Build outputs
    "dist/", "build/", ".next/", ".nuxt/", ".turbo/",
    # Python
    "__pycache__/", ".pytest_cache/", ".mypy_cache/", ".ruff_cache/",
    ".venv/", "venv/",
    # Caches / tooling
    ".cache/", "target/", ".git/",
)
```

These are filtered *by default*. Internal callers that genuinely need
them (deliverable archiver, file-tree exporter for the user) pass
`include_noise=True`.

## Why "just sort" doesn't save you

Sorting puts `node_modules/` *before* root files alphabetically (because
`n` < `p`/`s`). With 5000+ noise entries, the actual project files are
near the bottom. Truncation by first-N evicts them. Reverse sort moves
them to the top instead but breaks intuitive ordering for humans.

The filter is sort-order-independent and doesn't trade off legibility.

## When this trap shows up

Anywhere an LLM gets a list with a truncation cap:

- "What files exist?" — directory listing for a worker / replanner
- "What's currently in the index?" — search results truncated to top-K
- "What APIs does this service expose?" — endpoint list
- "What previous deliverables shipped?" — provenance list filtered by
  recency

The pattern: **list comes from a generator with a hidden long tail of
boilerplate; cap is set with the visible items in mind; long tail
silently displaces the visible items at truncation**.

Audit any LLM-facing list with this checklist:

1. Is there a truncation cap?
2. Could the *unfiltered* list contain a large tail of mechanical /
   boilerplate items (auto-generated files, framework metadata, build
   artifacts)?
3. If yes: filter at *production*, not *consumption*.

## Symptom checklist (you've hit this trap)

- The model picks the same phase / directive twice with no apparent
  reason.
- The model "ignores" rules about checking existing state.
- Output quality drops sharply when a project grows past first
  scaffold (because that's when noise dirs first appear).
- Manually inspecting the prompt (or its dump) shows the relevant
  signal *isn't there*. The bug is upstream of the prompt.

If you see any of these, look at what the listing actually contained
before blaming the prompt.
