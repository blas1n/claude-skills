---
name: shared-directory-namespace-collision
description: When a new feature introduces strict-naming sub-trees under an existing top-level directory that legacy code already writes to, recursive scans crash on legacy files unless the scan filters to canonical patterns first. Local unit tests pass on empty fixtures; CI fails the moment a real seeded vault/repo exists.
---

# Shared-directory namespace collision

## Trigger

You are about to add a new feature that defines a strict file-path schema under an existing top-level directory. Examples:

- A new typed-action layer using `actions/<kind>/<file>.md` while a legacy logger writes `actions/{YYYY-MM-DD}.md`
- A canonicalization layer adding `concepts/<state>/<id>.md` under a vault that already has user-created notes in `concepts/`
- A new schema-versioned migration system writing `migrations/v2/<n>.sql` while old code writes `migrations/<n>.sql`

If your scan code is "list every `.md` under `actions/` and parse it as a typed action," you have this collision.

## The failure mode

Local unit tests use empty fixtures or seed only the new schema's files — they pass. But:

- Demo CI seeds a realistic vault/repo with legacy artifacts → first request crashes
- Existing users upgrade and find the gateway hangs at startup → recovery requires manual cleanup
- The crash bubbles all the way up to the FastAPI lifespan and turns into "socket hang up" on every request, which masquerades as a network problem

The error message is usually unambiguous (`ValueError: not an action path: 'actions/2026-05-06_run.md'`), but it shows up only in the demo CI's "backend logs (on failure)" step — not in any unit test run.

## The fix pattern

**Filter to canon-shaped paths BEFORE calling the strict reader.** Do not make the reader lenient; that hides real bugs in service-side calls. Add a predicate at the scan layer.

```python
# index.py — module-level predicates, used wherever we walk shared dirs

_KNOWN_ACTION_KINDS: frozenset[str] = frozenset(models.ACTION_KINDS)


def _is_canon_action_path(path: str) -> bool:
    """``actions/<kind>/...md`` where ``<kind>`` is a known action kind."""
    parts = PurePosixPath(path).parts
    if len(parts) < 3 or parts[0] != "actions":
        return False
    if parts[1] not in _KNOWN_ACTION_KINDS:
        return False
    if not path.endswith(".md"):
        return False
    # Special-case for nested kinds (e.g. create-decision/<decision-kind>/)
    return not (
        parts[1] == "create-decision"
        and (len(parts) < 4 or parts[2] not in paths.DECISION_KINDS)
    )
```

Apply at every recursive walk site:

```python
# WRONG — crashes on legacy files
for path in await storage.list_files("actions"):
    action = await store.read_action(path)  # raises on legacy

# RIGHT — predicate filters first
for path in await storage.list_files("actions"):
    if not _is_canon_action_path(path):
        continue
    action = await store.read_action(path)
```

Same pattern for `_reload_path` (live invalidation): when an event arrives for a non-canon path, return early instead of trying to read it.

## Regression test recipe

The unit test that catches this MUST seed both a legacy file and a canon file in the same vault, then assert:

1. `rebuild_from_vault` does not raise.
2. The canon file is indexed.
3. The legacy file is NOT indexed.

```python
@pytest.mark.asyncio
async def test_rebuild_with_legacy_action_log_does_not_crash(storage):
    # The exact path the demo seeder writes (recreate the CI failure)
    await storage.write("actions/2026-05-06_run.md", "# legacy log\n")
    await storage.write("actions/input-log/2026-05-06.md", "# legacy input\n")

    store = NoteStore(storage)
    canon_path = "actions/create-concept/20260507-140000-ml.md"
    await store.write_action(models.ActionEntry(path=canon_path, kind="create-concept", ...))

    index = InMemoryCanonicalizationIndex()
    await index.initialize(storage)  # MUST NOT raise

    actions = await index.list_actions(kind="create-concept")
    assert len(actions) == 1
    assert all("2026-05-06_run" not in a.path for a in await index.list_actions())
```

The first time you write this test, it will fail — that's the point. Once it passes, it pins the contract for every future top-level dir share.

## Audit checklist before adding a new sub-tree

Before merging a feature that walks `<dir>/**`:

1. `grep -rn '<dir>/' bsage/ | grep -v <new_module>` — what else writes here?
2. For every existing writer found, list one example file path. Compare its shape against your new schema.
3. If the shapes overlap (same `.md` extension, same depth, same prefix), add a predicate filter at the walk site.
4. Add the regression test above with the actual legacy path string from step 2 (e.g. `"actions/2026-05-06_run.md"` — not a generic placeholder).
5. Run the test locally; confirm it fails before your fix and passes after.

## Why this trap is recurring

- Recursive `list_files()` is a one-line API that hides what shape it returns.
- Spec-driven schemas are usually written from a clean-vault assumption.
- Demo seeders / e2e fixtures live in a different directory from unit tests, so the collision shows up only at integration time.
- The error message says "not an action path" but the actual problem is "not a CANON action path — but a legacy one we should ignore."

When you see "everything works locally but CI demo crashes at startup," check directory-share collisions first.
