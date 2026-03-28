---
name: ralph-loop-prompt-passthrough
description: "Shell argument limits truncate long prompts passed to devcontainer exec — read prompt from file inside container instead"
---

# Ralph Loop Prompt Passthrough

## Trigger
When ralph-loop.sh or similar automation passes a long prompt to `claude -p` via `devcontainer exec`.

## Problem
Long PROMPT.md content passed as a shell argument to `devcontainer exec -- claude -p "$PROMPT"` gets truncated or corrupted. The `$()` subshell + shell escaping + devcontainer exec argument forwarding chain silently drops content.

**Symptoms:**
- `claude -p` runs but completes 0 tasks
- Ralph-loop exits with exit code 0 but no progress
- Output file is nearly empty

## Solution

**Wrong** — passing prompt as shell argument:
```bash
PROMPT=$(cat "$PROMPT_FILE")
OUTPUT=$(devcontainer exec --workspace-folder "$WORKSPACE" -- \
  npx -y @anthropic-ai/claude-code -p "$PROMPT" --allowedTools "...")
```

**Right** — reading prompt inside the container:
```bash
OUTPUT=$(devcontainer exec --workspace-folder "$WORKSPACE" -- \
  bash -c 'cd /workspace && claude -p "$(cat .agent/PROMPT.md)" --allowedTools "..."')
```

Key differences:
1. `cat` runs inside the container, not on the host
2. `claude` is called directly (already installed in container), not `npx`
3. `cd /workspace` ensures correct working directory

## Why
Shell argument passing through multiple layers (host shell → docker exec → container shell → claude) has compounding escaping/length issues. Reading from file inside the container bypasses all of this.
