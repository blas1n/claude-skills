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
- [ ] Convert ALL of them to VARCHAR before DROP TYPE
- [ ] Do data migration while columns are VARCHAR
- [ ] Recreate enum with the desired values
- [ ] Convert ALL columns back to enum with `USING column::enumtype`
- [ ] Write matching downgrade that reverses the process

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
