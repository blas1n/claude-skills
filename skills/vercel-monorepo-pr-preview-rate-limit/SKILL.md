---
name: vercel-monorepo-pr-preview-rate-limit
description: Vercel Hobby plan caps deploys at 100/day. Multi-project monorepos (prod + demo + … per app) burn through it in a few PR rounds. Disable PR previews via vercel.json ignoreCommand — ignored builds don't count.
version: 1.0.0
category: trap
---

# Vercel Hobby — PR Preview Rate Limit Trap

## Problem

Vercel's Hobby plan caps **deployments** at 100/day per account.
Each push to a connected branch triggers a deploy *per Vercel project pointed at that repo* — for a monorepo with `<app>` + `<app>-demo` projects on 4 apps, **one PR push = 8 deploys**.

A few rounds of dependency bumps + coordinated config changes across the apps will silently exhaust the quota. After that:

```
gh api repos/<owner>/<repo>/commits/main/statuses
> { "context": "Vercel – <project>",
>   "state": "failure",
>   "description": "Deployment rate limited — retry in 24 hours." }
```

The hard "retry in 24 hours" message is sticky for 24h regardless of additional pushes — even main pushes get rejected. The only relief is to wait or upgrade.

증상:
- "Deployment rate limited — retry in 24 hours" on commit statuses
- Successful merges to `main` produce no Vercel deploys
- Production sites stuck on the previous bundle (`x-vercel-cache: HIT` with high `age`) even after merging fixes

## Root cause

Each Vercel project listens for the **same** GitHub repo events. `git push origin pr-branch` = N project deploys, where N = number of Vercel projects bound to that repo. **Every PR preview counts** toward the daily 100-deploy cap.

## Solution

Disable PR-preview builds via `vercel.json` so only `main` deploys trigger Vercel. Per Vercel docs, builds skipped by `ignoreCommand` **do not count** against the rate limit.

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "ignoreCommand": "if [ \"$VERCEL_GIT_COMMIT_REF\" = \"main\" ]; then exit 1; else exit 0; fi"
}
```

Convention is inverted: **exit 1 = continue building, exit 0 = skip**.

Place `vercel.json` at the project's *Root Directory* (Vercel dashboard → Settings → General). For Next.js/Vite apps under `<repo>/frontend/` with Vercel root pointed at `frontend/`, it goes at `frontend/vercel.json`.

When two Vercel projects share the same root (e.g. `<app>-app` and `<app>-demo-app` both pointed at `frontend/`), one `vercel.json` covers both — both will skip non-main pushes.

### Validation

After landing the change, push a no-op PR. Check:

```bash
gh api repos/<owner>/<repo>/commits/<pr-branch-sha>/statuses --jq '.[] | select(.context | startswith("Vercel"))'
# expect: no Vercel statuses on the PR branch (or "Ignored" status)
```

Then push to `main`:

```bash
gh api repos/<owner>/<repo>/commits/main/statuses --jq '.[] | select(.context | startswith("Vercel"))'
# expect: state=pending → success
```

## Key insights

- The 24h cap is **per account**, not per project. Multi-project monorepos amplify the problem because every project deploys for every push.
- `ignoreCommand` runs inside the per-project Build & Output settings — both projects sharing a Root Directory inherit the same `vercel.json`.
- Once rate-limited, **even the fix** doesn't deploy until the cap resets. Land the `ignoreCommand` PR before you start a multi-bump round, not after you've already exhausted the quota.
- GitHub commit statuses include the failure reason in `.description` ("Deployment rate limited — retry in 24 hours") — read it before assuming Vercel webhook is broken.
- If Vercel later seems to silently miss a deploy on main (zero Vercel statuses on the commit), an empty commit (`git commit --allow-empty`) re-fires the webhook and is the simplest nudge.

## Red flags

- Production demo serving stale bundle hours after merge, `x-vercel-cache: HIT` with `age: 9000+`
- `gh api .../statuses` shows `Vercel – <project>: failure` with the 24-hour message
- A round of N consecutive PR+bump merges with no proportional change to the live site

## Related

- `~/.claude/skills/uv-git-dependency-cache-trap` — analogous "version pinned, change not visible" trap on the dependency layer
