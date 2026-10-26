---
name: idempotent-create-fallback-returns-the-stale-object
description: "An idempotent create (POST → 409/422 'already exists' → look up and return the existing object) silently keeps the FIRST attempt's mutable fields. When a later delivery recomputes derived content (a PR body with `Closes #N`/`Refs #N`, a ticket description, a release note), the re-delivery 'succeeds' but the object still claims what the first attempt delivered. Make the fallback update the fields the caller rebuilt, fail-soft."
version: 1.0.0
task_types: [review, debugging, design]
triggers:
  - pattern: "create endpoint that treats 409/422 'already exists' as success and returns the existing object"
  - pattern: "re-delivery / retry / re-drive pushes to the same branch, ticket, or resource"
  - pattern: "derived text (status line, checklist, Closes/Refs, summary) is rendered at delivery time"
  - pattern: "a merged PR closed an issue it should only have referenced"
category: trap
---

# Idempotent create keeps the stale object

## Problem
`open_pr` was idempotent on the head branch: GitHub answers `POST /pulls` with 422 "already
exists", the client looks up the open PR and returns it. Correct for "don't fail the retry" —
but the body the caller just built is **discarded**. bsvibe-app (#1244, 2026-10-26): the PR body
carries a requirements-ledger table and `Closes #N` only when every item is done. Attempt 1:
all done → `Closes #N`. A review comment re-opens the run, the agent defers one item, re-delivers
to the same branch → 422 → existing PR returned unchanged → still `Closes #N` → merging closes the
issue with work missing. Every test of the retry path was green: they asserted "returns the
existing PR", never "the PR now says what this delivery says".

## Fix
On the "already exists" branch, PATCH the fields the caller recomputes (title/body), and fall
back to the unchanged object if the PATCH is refused — the idempotency guarantee (the retry does
not fail) stays, the content follows the newest delivery.

```python
if resp.status_code == 422:
    existing = await self._find_open_pr_for_head(owner, repo, head)
    if existing is not None:
        try:
            return await self.update_pr(owner, repo, int(existing["number"]), title=title, body=body)
        except Exception:  # the PR exists; its old body is the fallback
            return existing
```

## Guard
A test on the retry path that asserts the UPDATE request carries the new body
(`json.loads(patch.calls.last.request.content) == {"title": ..., "body": ...}`), plus one where the
update fails and the existing object is still returned. Cut the update line → the first goes red.

## Ask in review
For every "already exists → return existing": which fields did the caller just compute, and does
anything downstream read them from the object (a merge closing issues, a UI, a watcher)?
