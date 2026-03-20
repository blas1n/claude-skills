---
name: sql-join-or-count-trap
description: SQL JOIN with OR clause causes double-counting in COUNT(*) — use COUNT(DISTINCT id) instead
---

# SQL JOIN OR Count Trap

## Problem

`COUNT(*)` with a `JOIN ... ON A OR B` clause silently inflates results when multiple entities match the same row from different sides of the OR.

- 증상: Count query returns inflated numbers (e.g. 4 instead of 2) — tests pass because assertions use `>=` instead of `==`
- 근본 원인: `JOIN entities e ON e.id = r.source_id OR e.id = r.target_id` creates a cross-product when both sides match entities with the same filter criteria (e.g. same `source_path`)
- 흔한 오해: "OR in JOIN works like UNION" — it doesn't, it multiplies rows

## Example

```sql
-- WRONG: double-counts when both endpoints share source_path
SELECT COUNT(*) FROM relationships r
JOIN entities e ON e.id = r.source_id OR e.id = r.target_id
WHERE e.source_path = ?

-- Entity A (source_path='a.md'), Entity B (source_path='a.md')
-- Relationship: A→B
-- JOIN matches: (r, A via source_id) AND (r, B via target_id)
-- COUNT(*) = 2, but only 1 relationship exists
```

## Solution

Two approaches, depending on intent:

### Option 1: COUNT(DISTINCT) — count unique relationships
```sql
SELECT COUNT(DISTINCT r.id) FROM relationships r
JOIN entities e ON e.id = r.source_id OR e.id = r.target_id
WHERE e.source_path = ?
```

### Option 2: UNION subqueries — count inbound + outbound separately
```sql
SELECT COUNT(*) FROM (
    SELECT r.id FROM relationships r
    JOIN entities e ON e.id = r.source_id WHERE e.source_path = ?
    UNION
    SELECT r.id FROM relationships r
    JOIN entities e ON e.id = r.target_id WHERE e.source_path = ?
)
```

Use UNION (not UNION ALL) to deduplicate self-referencing relationships.

## Key Insights

- `JOIN ... ON A OR B` is NOT equivalent to two separate JOINs merged — it creates a cross-product of all matching rows
- Tests using `assert count >= N` (loose assertions) hide this bug — always use exact `assert count == N` for count queries
- This pattern is especially dangerous in graph databases where both endpoints of a relationship can share properties (same source_path, same type, etc.)

## Red Flags

- `JOIN ... ON ... OR ...` combined with `COUNT(*)` or `SUM()` — always suspect double-counting
- Count-based tests that use `>=` instead of `==` — the loose assertion may be hiding inflated results
- Maturity/scoring systems that count relationships — wrong counts cascade into wrong scores
