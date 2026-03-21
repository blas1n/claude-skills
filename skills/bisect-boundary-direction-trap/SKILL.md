---
name: bisect-boundary-direction-trap
description: "bisect_left vs bisect_right confusion when clamping values to interval boundaries — choosing wrong direction silently inverts ranges"
triggers:
  - Using bisect_left or bisect_right for boundary clamping
  - Clamping segment/interval end times to partition boundaries
  - Binary search on sorted boundary arrays
---

# bisect_left vs bisect_right: Boundary Clamping Direction Trap

## The Trap

When you have a sorted array of **interval end-points** (boundaries) and need to find which interval a value belongs to, `bisect_left` and `bisect_right` give different results **only when the value exactly equals a boundary**. Choosing wrong silently produces inverted ranges (`start > end`).

## Mental Model

Given partitions defined by their END times:

```
Scene 0: [0.0, 5.0)    boundary[0] = 5.0
Scene 1: [5.0, 8.0)    boundary[1] = 8.0
```

**Question**: "Which boundary should clamp `seg.start = 5.0`?"

The segment starting at 5.0 belongs to **Scene 1**, so it should be clamped to **boundary[1] = 8.0** (Scene 1's end).

```python
bisect_left([5.0, 8.0], 5.0)   # → 0  → boundary = 5.0  WRONG (previous scene's end)
bisect_right([5.0, 8.0], 5.0)  # → 1  → boundary = 8.0  CORRECT (current scene's end)
```

`bisect_left` returns the index OF the matching value → points to the **previous** interval's end.
`bisect_right` returns the index AFTER the matching value → points to the **current** interval's end.

## The Rule

> When boundaries are **end-points** of intervals and you want to find **which interval a value falls into**, use `bisect_right`.
> When boundaries are **start-points** and you want the interval **starting at or after** the value, use `bisect_left`.

| Boundary semantics | "Which interval owns this value?" | Use |
|---|---|---|
| End-points `[end_0, end_1, ...]` | Find the interval this value belongs to | `bisect_right` |
| Start-points `[start_0, start_1, ...]` | Find the interval starting at or before | `bisect_right - 1` |

## Why This Is Hard to Catch

- For values NOT on a boundary, both functions give the same result.
- Tests with "nice" numbers (1.0, 2.5, 3.7) pass with either function.
- Only boundary-exact values (common at scene transitions) trigger the bug.
- The symptom is a silently inverted range (`start=5.0, end=4.98`) that may be clamped to zero-duration downstream, making it invisible in output.

## Verification Checklist

When reviewing bisect usage for boundary clamping:

1. **Identify boundary semantics**: Are boundaries start-points or end-points?
2. **Test the exact-boundary case**: What happens when `value == boundary[i]`?
3. **Check for range inversion**: Can `start > end` result from the clamped value?
4. **Add a test case at exact boundaries**: Always include `seg.start = boundary_value` in tests.

## Real-World Example (BSForge subtitle clamping)

```python
# WRONG — bisect_left clamps scene-1 segments to scene-0's end
idx = bisect_left(scene_boundaries, seg.start)  # seg.start=5.0 → idx=0 → boundary=5.0
if seg.end > boundary:
    seg.end = boundary - margin  # 5.0 - 0.02 = 4.98, but seg.start=5.0 → INVERTED

# CORRECT — bisect_right finds the current scene's end
idx = bisect_right(scene_boundaries, seg.start)  # seg.start=5.0 → idx=1 → boundary=8.0
```

## Origin

Discovered during BSForge feature/resource review. Initial reviewer suggested `bisect_right → bisect_left` as a "fix" — this was wrong and introduced a bug. Sub-agent review caught the inversion. Root cause: confusing "boundary this value matches" with "interval this value belongs to."
