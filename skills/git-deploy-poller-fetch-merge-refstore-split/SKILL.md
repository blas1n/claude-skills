---
name: git-deploy-poller-fetch-merge-refstore-split
description: A git-based deploy poller that `git fetch`es in one directory but `git merge`s in another silently no-ops — and rebuilds stale code forever — when the two directories don't share a ref store. Happens when one project's working dir is a standalone clone instead of a worktree of the shared bare repo the poller fetches into.
metadata:
  type: reference
---

# Git deploy poller — fetch-here, merge-there ref-store split

## Symptom

A cron/launchd auto-deploy poller logs the SAME commit being "deployed"
over and over, every interval, forever:

```
[BSupervisor] Deploying aa9a7b4...
Already up to date.
... (rebuild) ...
[BSupervisor] Done
[BSupervisor] Deploying aa9a7b4...   ← again, ~4 min later
```

The container is rebuilt every cycle but from **stale code** — the merge
that should advance the working tree reports `Already up to date` even
though the working tree HEAD is demonstrably behind the remote.

## Root cause

The poller is typically written like:

```bash
BARE=~/Works/$name/.bare
WORK=~/Works/$name/main
git -C "$BARE" fetch origin main          # fetch into the BARE repo
LOCAL=$(git -C "$WORK" rev-parse HEAD)
REMOTE=$(git -C "$BARE" rev-parse origin/main)
[ "$LOCAL" != "$REMOTE" ] && git -C "$WORK" merge origin/main --ff-only
```

This is correct **only if `$WORK` is a linked worktree of `$BARE`** — then
they share one object DB and one set of refs, so `origin/main` resolves to
the same SHA in both.

If `$WORK` is instead a **standalone clone** (its own `.git`, its own
`origin` remote), it has its own `refs/remotes/origin/main`. The poller
never fetches *that* clone, so its `origin/main` stays frozen at whatever
it was last fetched. Then:

- `REMOTE` (from `$BARE`) = new SHA  → `LOCAL != REMOTE` is true
- `git -C "$WORK" merge origin/main` uses `$WORK`'s **stale** `origin/main`
  → `Already up to date` → HEAD never advances
- next cycle: same thing → infinite stale rebuild loop

The build context (`docker-compose up --build`) is `$WORK`, so every
rebuild ships the OLD code while the `.deployed` state file gets bumped to
the new SHA — masking the failure.

## How to detect

```bash
git -C "$WORK" worktree list          # a worktree-of-.bare lists siblings;
                                      # a standalone clone lists only itself
git -C "$WORK" rev-parse origin/main  # compare to git -C "$BARE" rev-parse origin/main
git -C "$WORK" remote -v              # standalone clone has its own origin URL
```

If `$WORK`'s `origin/main` ≠ `$BARE`'s `origin/main`, you've found it.

## Fix

**Immediate (unblock one project):** fetch in the clone itself, then merge:

```bash
git -C "$WORK" fetch origin main
git -C "$WORK" merge origin/main --ff-only
# then rebuild once manually — the poller will skip it now that
# LOCAL == REMOTE == .deployed:
docker-compose -p <proj> -f deploy/docker-compose.yml up -d --build --force-recreate
```

Pause the poller (`launchctl unload …`) while doing this so it doesn't
race the manual `docker-compose`; re-enable after.

**Root cause:** make every project's working dir a real worktree of the
shared bare repo, OR make the poller `git fetch` in `$WORK` (not just
`$BARE`). One project being a standalone clone while the rest are worktrees
is the silent inconsistency — audit all of them.

## Generalizes to

Any "fetch refs in location A, act on them in location B" automation where
A and B are assumed to share a ref store but one drifted into being a
separate repo. The fix is always: fetch where you merge, or guarantee a
shared ref store.
