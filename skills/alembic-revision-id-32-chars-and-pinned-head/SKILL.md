---
name: alembic-revision-id-32-chars-and-pinned-head
description: Adding an Alembic revision — the id is capped at 32 chars by `alembic_version.version_num` (a longer one fails at the UPDATE, not at your DDL), and repos commonly pin the head revision as a literal string in MORE THAN ONE test file, so fixing the one you found still fails CI.
category: trap
---

# Alembic: 32-char revision id + head pinned in several places

## Problem

Two independent traps hit on the same action — adding one migration.

### 1. `revision` longer than 32 characters

Alembic creates `alembic_version.version_num` as `VARCHAR(32)`. A descriptive id
overruns it easily:

```python
revision: str = "oauth_access_token_nullable_expiry"   # 34 chars
```

`upgrade head` then dies **after** your DDL succeeded, on the bookkeeping write:

```
sqlalchemy.exc.DBAPIError: <asyncpg.exceptions.StringDataRightTruncationError>:
  value too long for type character varying(32)
[SQL: UPDATE alembic_version SET version_num='oauth_access_token_nullable_expiry'
      WHERE alembic_version.version_num = 'executor_task_execution_target']
```

Two things make this misleading:

- the error names a **data** problem, so it reads like a row/column issue in the
  table you were migrating, not like "your revision id is too long";
- SQLite-only test runs never see it. It needs a real Postgres.

### 2. The head revision is pinned as a literal in more than one test

Repos that guard the migration chain typically assert the current tip by string.
Those assertions live in **several** files, and a repo-wide grep is the only way
to know how many:

```
tests/test_alembic_fresh.py:128   assert stamped == "executor_task_execution_target"
tests/test_alembic_fresh.py:138   assert stamped == "executor_task_execution_target"   # re-upgrade phase
tests/test_alembic_parse.py:123   assert "executor_task_execution_target" in result.stdout
```

Fixing the file whose failure you happened to see leaves the rest red. If the
remaining one is skipped locally (or your local run never reached it), CI is
where you find out — one full pipeline later.

## Solution

When adding a migration, do all four before pushing:

1. **Keep the revision id ≤ 32 chars.** Check it, don't eyeball it:
   ```bash
   python3 -c "r='oauth_token_nullable_expiry'; print(len(r), 'OK' if len(r)<=32 else 'TOO LONG')"
   ```
   Drop redundant words (`oauth_access_token_…` → `oauth_token_…`) rather than
   abbreviating into something unreadable.

2. **Sweep every pinned head, not just the failing one.** Grep for the id you
   are replacing, across the whole test tree:
   ```bash
   grep -rn "<previous_head_revision_id>" tests/ --include="*.py"
   ```
   Update each hit. Expect two or more. Note some hits are legitimate
   (`_alembic(["downgrade", "<previous_head>"])` targets a parent on purpose) —
   read each before editing.

3. **Confirm a single head:**
   ```bash
   uv run --extra dev alembic heads     # exactly one line, ending "(head)"
   ```

4. **Run the fresh-PG smoke test**, which is what actually catches trap 1:
   ```bash
   uv run --extra dev pytest tests/test_alembic_fresh.py -q
   ```
   SQLite cannot reproduce it; a real Postgres can. See
   `alembic-fresh-pg-smoke-test` for why that suite is worth keeping.

## Also worth writing into the migration

If the new column is nullable to express something semantic ("NULL = never
expires"), the reverse migration cannot honestly re-impose `NOT NULL` once such
rows exist. Fail loudly instead of inventing a value:

```python
def downgrade() -> None:
    bind = op.get_bind()
    orphans = bind.execute(
        sa.text("SELECT COUNT(*) FROM oauth_access_tokens WHERE expires_at IS NULL")
    ).scalar_one()
    if orphans:
        raise RuntimeError(
            f"{orphans} row(s) have a NULL expires_at. Revoke them or set an explicit "
            "value before downgrading past this revision."
        )
    op.alter_column(..., nullable=False)
```

## Related

- `alembic-fresh-pg-smoke-test` — the suite that catches the length trap
- `alembic-phantom-revision-from-unpushed-branch` — stamping a head that only exists locally
- `supabase-migration-version-collision-silent-rollback`
