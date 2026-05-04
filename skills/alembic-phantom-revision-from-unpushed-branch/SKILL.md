---
name: alembic-phantom-revision-from-unpushed-branch
description: "Running alembic upgrade from an unpushed local branch against a shared/prod DB stamps an unresolvable revision. Container reboots into restart loop with `Can't locate revision identified by '<id>'`. Diagnose schema impact before resetting alembic_version."
version: 1.0.0
task_types: [debugging, devops]
triggers:
  - pattern: "alembic upgrade head fails with `Can't locate revision identified by '<hex>'` and the revision file is missing from the repo"
  - pattern: "container restart loop after a deploy where the only error is alembic missing a revision id"
---

# Alembic Phantom Revision from Unpushed Branch

## Symptom

A backend container hits a restart loop. Logs show:

```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
ERROR [alembic.util.messaging] Can't locate revision identified by 'l4e5f6a7b8c9'
FAILED: Can't locate revision identified by 'l4e5f6a7b8c9'
```

`docker inspect <container> --format '{{.RestartCount}}'` shows the container has been crashing for hours or days — long before whatever change you're investigating now.

## Why

A developer (often you, days ago) ran `alembic upgrade head` from a feature branch *that was never pushed*. Workflow:

1. Local branch `feat/foo` adds migration `<rev>` (e.g. `l4e5f6a7b8c9`).
2. They start that branch's container against the **shared dev/prod DB**.
3. Alembic runs `INSERT INTO alembic_version VALUES ('<rev>')`.
4. Branch is abandoned — no PR, no push.
5. Main keeps moving forward without `<rev>`.
6. Next time *anyone* boots a main-based container, alembic reads `alembic_version`, can't find the revision file, refuses to upgrade.

The DB is not actually broken — only the alembic stamp is. **The migration's schema changes may or may not have been applied** to the DB, depending on how far the upgrade got.

## Diagnosis

```bash
# 1. What does the DB think it's on?
docker exec <pg-container> psql -U <user> -d <db> -c "SELECT version_num FROM alembic_version;"
# → l4e5f6a7b8c9

# 2. Is that revision in the repo (any branch, locally or remote)?
git log --all --oneline -- '*<rev>*' '**/alembic*versions/*'
git branch -r --contains <rev-related-commit>   # if you find it via git log -S
git log --all --oneline -S "<rev>"              # search commit content

# 3. If git log finds the commit but `git branch -r --contains` is empty,
#    the commit exists only in a local branch — nobody else has it.
#    git stash list / git reflog can confirm it's truly orphaned.

# 4. What's the real head on the current main?
python3 <<'PY'
import re, pathlib
versions = pathlib.Path('alembic/versions').glob('*.py')
revs = {}
for f in versions:
    text = f.read_text()
    rev = re.search(r"^revision\s*:\s*str\s*=\s*['\"]([^'\"]+)['\"]", text, re.M)
    if not rev:
        rev = re.search(r"^revision\s*=\s*['\"]([^'\"]+)['\"]", text, re.M)  # legacy form
    if not rev: continue
    rid = rev.group(1)
    down = re.search(r"^down_revision\s*:[^=]*=\s*(.+)$", text, re.M)
    downs = []
    if down:
        for q in re.findall(r"['\"]([^'\"]+)['\"]", down.group(1)):
            downs.append(q)
    revs[rid] = downs
all_downs = set()
for d in revs.values(): all_downs.update(d)
heads = [r for r in revs if r not in all_downs]
print(f"main heads: {heads}")
PY
```

## Critical: schema impact analysis BEFORE stamp reset

You must know whether the phantom migration's `upgrade()` actually mutated the DB schema. If it did, a stamp-only reset leaves the DB in a state main's history doesn't describe — the next migration that touches the same column/table will fail or produce wrong data.

If you have access to the original migration file (sitting in the developer's worktree, in their git stash, or in a draft PR), read its `upgrade()`:

- **Pure DDL the migration adds** (CREATE/ALTER/DROP). Check each one against the live DB. If the change *is* present in the DB but absent from main's schema, you have drift.
- **Data migration** (UPDATE/INSERT). These you may not be able to detect by inspecting structure alone — you need a domain check.

If you cannot find the original migration file:

- Inspect the suspicious tables (the migration's docstring or commit message usually hints what it touched). `\d <table>` in psql.
- Compare to the current main schema (the most recent migration's `upgrade()` body, or a schema dump from a fresh PG bootstrapped via `alembic upgrade head` against an empty DB).
- If the suspect column/index/table looks identical to main → safe to stamp-reset.
- If anything differs → DO NOT stamp-reset. Either:
  - Recover the missing migration file (from local worktree, stash, or by asking the developer who made it) and merge it properly via a PR.
  - Or hand-write a downgrade SQL to reverse the schema delta, then stamp-reset.

## Fix (after schema impact is confirmed clean)

```bash
docker exec <pg-container> psql -U <user> -d <db> \
  -c "UPDATE alembic_version SET version_num = '<main_head_id>';"
docker-compose -p <project> -f <compose> up -d --no-deps --force-recreate app
docker logs --tail 30 <app> | grep -E "alembic|started"
# expect: "Will assume transactional DDL." then app boots normally
```

## Prevention

- **Never run alembic upgrade from a local-only branch against a shared DB.** Use a per-developer or per-branch DB instance (devcontainer's compose file usually provisions one).
- If you have to test a migration against a shared DB:
  1. Push the branch first (so the revision is recoverable).
  2. Run `alembic upgrade head`.
  3. **Before abandoning the branch**, run `alembic downgrade <prior_main_head>`.
- CI gate: a fresh-PG smoke test (`alembic upgrade head` against an empty PG) catches missing revisions in the *repo*, but does NOT catch this trap because the offending revision never reached the repo. The trap is in the *DB*, not the code.

## Operational gotcha

If multiple developers share a dev/staging DB and everyone runs migrations from feature branches, this trap accumulates silently. The first sign is when **someone else's branch** restart-loops on alembic, not the developer who created the phantom revision. Plan for rapid recovery procedures (this skill) rather than expecting prevention to be perfect.
