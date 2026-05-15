---
name: alembic-enum-create-type-trap
description: Alembic migration adding a Postgres ENUM column emits CREATE TYPE twice (DuplicateObjectError) even with sa.Enum(create_type=False) — must use postgresql.ENUM(create_type=False) for the column-side reference.
---

# Alembic Enum CREATE TYPE Trap

## Symptom

Adding a new Postgres `ENUM` type in an alembic migration that also creates a table with that enum as a column type. Migration fails on fresh PG with:

```
sqlalchemy.exc.ProgrammingError: <class 'asyncpg.exceptions.DuplicateObjectError'>:
type "<enum_name>" already exists
[SQL: CREATE TYPE <enum_name> AS ENUM (...)]
```

…even though the migration explicitly calls `Enum.create(checkfirst=True)` first, and even though the column-side `sa.Enum(..., create_type=False)` should suppress the second create.

## Cause

`sa.Enum(values, name="x", create_type=False)` does **not reliably** suppress the auto-create when the enum is referenced inside `op.create_table` — at least under the `asyncpg` dialect, alembic still emits `CREATE TYPE` a second time for the column type.

## Fix

Use **`postgresql.ENUM`** (from `sqlalchemy.dialects.postgresql`) for the column-side reference, and create the type up-front with a raw SQL DO-block guarded by `IF NOT EXISTS`:

```python
from sqlalchemy.dialects import postgresql
import sqlalchemy as sa
from alembic import op

_VALUES = ("queued", "running", "passed", "failed", "skipped", "error")


def upgrade() -> None:
    # 1. Create the type up-front. DO block is reusable / idempotent
    # and survives partially-failed prior attempts that left the
    # type in pg_type.
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'my_status') THEN "
        "CREATE TYPE my_status AS ENUM ('queued', 'running', 'passed', 'failed', 'skipped', 'error'); "
        "END IF; END $$;"
    )

    # 2. Use postgresql.ENUM (NOT sa.Enum) with create_type=False
    # for the column type. sa.Enum's create_type=False is unreliable
    # inside op.create_table on the asyncpg dialect.
    status_col = postgresql.ENUM(*_VALUES, name="my_status", create_type=False)

    op.create_table(
        "my_table",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("status", status_col, nullable=False, server_default="queued"),
        # ...
    )


def downgrade() -> None:
    op.drop_table("my_table")
    # Drop the type explicitly — alembic doesn't auto-drop named types.
    sa.Enum(name="my_status").drop(op.get_bind(), checkfirst=True)
```

## What does NOT work

- ❌ `sa.Enum(*values, name="x")` then `.create(bind, checkfirst=True)` — table-create still re-emits
- ❌ `sa.Enum(*values, name="x", create_type=False)` for column type — flag not honored under asyncpg dialect
- ❌ `op.create_table(..., sa.Column("x", sa.Enum(...)))` without pre-creating the type — table_create's auto-emit doesn't use `IF NOT EXISTS`

## Confirmation pattern

Local reproduction needs a **truly clean** PG state — `DROP SCHEMA public CASCADE` doesn't drop enum types:

```bash
# Drop both the schema *and* the dangling enum types
docker exec <pg> psql -U u -d db -c "
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
DROP TYPE IF EXISTS my_status CASCADE;
DROP TYPE IF EXISTS my_other_enum CASCADE;
"
```

Forgetting to drop types is itself a footgun — a previously-failed attempt leaves the type, and you can confuse "my migration is broken" with "my prior failed run left state."

## Why the existing fresh-PG smoke is essential

This trap is **completely invisible to SQLite-backed unit tests** (they use `Base.metadata.create_all`, not the migration). It only surfaces when alembic actually runs against PG. Always run the fresh-PG smoke before assuming a migration is sound:

```bash
cd backend && BSNEXUS_INTEGRATION_PG_URL="postgresql+asyncpg://..." \
  uv run --project . pytest tests/test_alembic_fresh_migration.py
```

## Case

- BSNexus PR #141 (multi-aspect verifier, 2026-05-15): hit this on fresh-PG locally AND on CI (`backend-test` + `demo-smoke` + `prod-build-smoke` all failed identically with `DuplicateObjectError` on `proof_aspect_type`). 466 unit tests passed because SQLite path uses `create_all`, not migration. Fixed by switching to `postgresql.ENUM(create_type=False)` + DO-block guarded `CREATE TYPE`.
