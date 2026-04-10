---
name: alembic-postgres-enum-migration
description: "Alembic + PostgreSQL Enum Migration — avoid ALTER TYPE ADD VALUE in migrations, use DROP/RECREATE pattern instead"
version: 1.0.0
---

# Alembic + PostgreSQL Enum Migration

## When to Use

When writing Alembic migrations that add, remove, or rename PostgreSQL enum values.
Especially critical when `alembic upgrade head` runs multiple migrations in a single transaction.

## Problem

PostgreSQL's `ALTER TYPE ... ADD VALUE` has a transaction-level restriction:

> New enum values added with `ADD VALUE` cannot be used in the **same transaction** they were created in.

This causes `asyncpg.exceptions.UnsafeNewEnumValueUsageError` when:
1. Migration A adds an enum value with `ADD VALUE`
2. Migration B (or even the same migration) uses that value in `UPDATE`/`INSERT`
3. Both run in the same `alembic upgrade head` transaction

## Solution: DROP/RECREATE Pattern

**NEVER use `ALTER TYPE ADD VALUE` in Alembic migrations.**

Instead, always use the DROP/RECREATE pattern:

```python
def upgrade() -> None:
    # 1. Convert ALL columns using this enum to VARCHAR
    op.execute("ALTER TABLE tasks ALTER COLUMN status TYPE VARCHAR(20)")
    op.execute("ALTER TABLE task_history ALTER COLUMN from_status TYPE VARCHAR(50)")
    op.execute("ALTER TABLE task_history ALTER COLUMN to_status TYPE VARCHAR(50)")

    # 2. Migrate data while columns are VARCHAR (safe, no enum constraints)
    op.execute("UPDATE tasks SET status = 'ready' WHERE status = 'rejected'")

    # 3. Drop old enum and create new one
    op.execute("DROP TYPE taskstatus")
    op.execute(
        "CREATE TYPE taskstatus AS ENUM "
        "('waiting', 'ready', 'queued', 'in_progress', 'review', 'done', 'redesign')"
    )

    # 4. Convert columns back to enum
    op.execute("ALTER TABLE tasks ALTER COLUMN status TYPE taskstatus USING status::taskstatus")
    op.execute("ALTER TABLE task_history ALTER COLUMN from_status TYPE taskstatus USING from_status::taskstatus")
    op.execute("ALTER TABLE task_history ALTER COLUMN to_status TYPE taskstatus USING to_status::taskstatus")
```

## Checklist

- [ ] Find ALL tables/columns using the target enum (not just the primary table)
- [ ] **`ALTER TABLE ... ALTER COLUMN ... DROP DEFAULT` BEFORE `ALTER COLUMN TYPE VARCHAR`** if any column has a default value of the enum type — see "DROP DEFAULT trap" below
- [ ] Convert ALL of them to VARCHAR before DROP TYPE
- [ ] Do data migration while columns are VARCHAR
- [ ] Recreate enum with the desired values
- [ ] Convert ALL columns back to enum with `USING column::enumtype`
- [ ] Re-`SET DEFAULT` after the type is back to the enum
- [ ] Write matching downgrade that reverses the process
- [ ] **Run the fresh-PG smoke test** (see `alembic-fresh-pg-smoke-test` skill) — SQLite tests cannot catch any of these traps

## DROP DEFAULT trap

If a column has a default value (`DEFAULT 'something'`) and that default is typed as the enum, `ALTER COLUMN TYPE VARCHAR` succeeds but the **default expression keeps the old enum type**. Then `DROP TYPE oldenum` fails with:

```
DependentObjectsStillExistError: cannot drop type oldenum because other objects depend on it
DETAIL: default value for column foo of table bar depends on type oldenum
```

**Fix**: drop the default *first*, do the type juggling, then re-set the default:

```python
op.execute("ALTER TABLE tasks ALTER COLUMN source DROP DEFAULT")
op.execute("ALTER TABLE tasks ALTER COLUMN source TYPE VARCHAR(20)")
# ... data migration, DROP TYPE, CREATE TYPE, ALTER COLUMN TYPE back to enum ...
op.execute("ALTER TABLE tasks ALTER COLUMN source SET DEFAULT 'llm'")
```

This trap is invisible in SQLite tests because SQLite has no enum types and no per-column type-bound defaults.

## Why Not `ADD VALUE`?

| Approach | Single migration | `upgrade head` (multi) | Data migration in same txn |
|----------|:---:|:---:|:---:|
| `ADD VALUE` | Works* | FAILS | FAILS |
| DROP/RECREATE | Works | Works | Works |

*Only if no UPDATE/INSERT uses the new value in the same migration.

## Key Insight

`alembic upgrade head` wraps all pending migrations in a single transaction by default.
Even if `ADD VALUE` and `UPDATE` are in separate migration files, they share the same transaction.
The DROP/RECREATE pattern avoids this entirely because it never uses `ADD VALUE`.

## Additional Trap: SQLAlchemy Model Enum DDL Listener

When `env.py` imports models with `Enum(PythonEnum)` columns, SQLAlchemy registers a metadata-level `before_create` DDL listener. Even if the migration uses `create_type=False` on its own Enum instance, `op.create_table()` triggers the model's listener which fires a bare `CREATE TYPE` without idempotency.

**Symptoms:** `DuplicateObjectError: type "enumname" already exists` on fresh DB or after partial migration.

**Fix:** Use raw SQL for enum creation in migrations:
```python
def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE suggestionstatus AS ENUM ('pending', 'approved', 'rejected', 'modified');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS task_suggestions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            status suggestionstatus NOT NULL DEFAULT 'pending',
            ...
        )
    """)
```

Also add `create_type=False` on the model column as defense:
```python
status: Mapped[SuggestionStatus] = mapped_column(
    Enum(SuggestionStatus, create_type=False), default=SuggestionStatus.pending
)
```
