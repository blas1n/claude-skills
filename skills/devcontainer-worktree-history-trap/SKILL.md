---
name: devcontainer-worktree-history-trap
description: "Devcontainer dotfiles can destroy git worktree history by running git init in workspace — use --dotfiles-target-path to isolate"
---

# Devcontainer Worktree History Trap

## Trigger
When using `devcontainer up` with `--dotfiles-repository` on a git worktree workspace.

## Problem
Devcontainer's dotfiles install script may run `git init` inside the workspace directory (`/workspace`), creating a new orphan git repository that replaces the worktree's `.git` file with a `.git/` directory. All parent history is lost.

**Symptoms:**
- `git log` shows only commits made inside the container
- PRs fail with "no history in common with base branch"
- `git format-patch` + `git am` needed to rescue commits

## Root Cause
The `--dotfiles-repository` option clones a dotfiles repo and runs its install script. Many dotfiles installers (e.g., chezmoi, yadm, or custom scripts) call `git init` as part of setup. When the working directory is `/workspace`, this overwrites the worktree's git linkage.

## Solution

1. **Always specify `--dotfiles-target-path`** to isolate dotfiles from workspace:
```bash
devcontainer up \
  --workspace-folder "$WORKSPACE" \
  --dotfiles-repository https://github.com/user/dotfiles.git \
  --dotfiles-target-path '~/.dotfiles'  # CRITICAL: isolate from workspace
```

2. **Verify git history after container creation** before running any work:
```bash
devcontainer exec --workspace-folder "$WORKSPACE" -- \
  bash -c 'cd /workspace && git log --oneline -1 && cat .git'
```
- `.git` should be a file (worktree pointer), NOT a directory
- `git log` should show the parent branch history

3. **If history is already destroyed**, recover via patch:
```bash
git format-patch --root -o /tmp/patches/
rm -rf "$WORKSPACE"
cd project/.bare && git worktree prune && git worktree add "$WORKSPACE" -b branch base-branch
cd "$WORKSPACE" && git am --3way --exclude='.agent/*' /tmp/patches/*.patch
```

## Why
`devcontainer up` assumes the workspace is a standalone project. Git worktrees use a `.git` file pointing to the bare repo's `worktrees/` directory — dotfiles installers don't account for this.
