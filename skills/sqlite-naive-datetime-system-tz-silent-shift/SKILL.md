---
name: sqlite-naive-datetime-system-tz-silent-shift
description: SQLite + SQLAlchemy `DateTime(timezone=True)` round-trip silently strips tzinfo. Downstream `.astimezone()` on the naive datetime then uses the SYSTEM tz, not UTC — silently shifts time-of-day classification by the local UTC offset (e.g. ~13h on a KST host, ~9h on JST, ~5h on EST). Symptom: bucket/window/cutoff classifiers (session hours, after-hours/overnight splits, daily aggregates) misclassify in production. Tests pass on the dev machine that happens to match the writer's intended tz; bug surfaces on any other host.
category: trap
---

# SQLite + naive datetime → system-tz silent shift

## Problem

Writers store UTC. SQLite (via SQLAlchemy `DateTime(timezone=True)`) drops the tzinfo on round-trip. Readers get back a naive datetime. Any downstream code calling `.astimezone(SOMEZONE)` on that naive value uses the **system tz** (per Python docs: "If self is naive, it is presumed to represent time in the system timezone.") — not UTC.

On a KST host (UTC+9), `2026-06-01 06:00 UTC` is stored, comes back naive `2026-06-01 06:00`, gets interpreted as `06:00 KST` = `21:00 previous-day UTC` = `17:00 previous-day EDT`. A "pre-market overnight" event becomes an "after-hours" event of the previous day. Every bucket shifts by the host's UTC offset.

The bug:
- Is invisible to type checkers (signatures still say `datetime`).
- Passes unit tests if the dev host's tz matches the writer's intended tz, or if tests build aware datetimes inline (skipping the DB round-trip).
- Silently misclassifies whole datasets in production logs / aggregates.

Surfaced in bloasis PR57 (mention forward-tracking): SQLAlchemy returned `tzinfo=None`, `classify_mention_timing(.).astimezone(ET)` on KST Mac Mini shifted every Trump-mention bucket. PR55/56 retrospective results were partially miscategorized for this reason.

## Detection

Three signals — any one means investigate:

1. Repro probe — write an aware UTC datetime through SQLAlchemy `DateTime(timezone=True)` on SQLite, read it back, check `tzinfo`:
   ```python
   ts = datetime(2026, 6, 1, 6, 0, tzinfo=UTC)
   writers.upsert(eng, ts=ts)
   row = conn.execute(select(table.c.ts)).fetchone()
   assert row.ts.tzinfo is not None  # FAILS — SQLite strips it
   ```
2. Wall-clock shift — events that should sit in bucket A consistently land in bucket B with an offset that matches the dev host's UTC offset.
3. Test/prod divergence — unit tests construct aware datetimes inline (`datetime(..., tzinfo=UTC)`) and pass; production data goes through the DB round-trip and misbehaves.

## Solution

Two layers, both required:

### 1. Writers must always store UTC

Non-negotiable. Any function that builds a stored timestamp normalizes to UTC at the boundary:

```python
def upsert_post(engine, *, posted_at: datetime, ...):
    if posted_at.tzinfo is None:
        raise ValueError("posted_at must be tz-aware")
    posted_at_utc = posted_at.astimezone(UTC)
    # ... insert posted_at_utc
```

If you skip this, the rest of the defense falls apart because "naive → assume UTC" downstream is a lie for any row whose original aware value wasn't UTC.

### 2. Downstream classifiers normalize naive → UTC defensively

Any function whose job is to interpret a stored timestamp's wall-clock position (session bucket, day-of-week, hour-of-day cutoffs) treats naive input as UTC, not system tz:

```python
def classify_session_bucket(ts: datetime) -> Bucket:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    et = ts.astimezone(ZoneInfo("America/New_York"))
    ...
```

This makes the function correct regardless of whether the caller passed a fresh aware UTC value or a SQLite-round-tripped naive one — both interpretations agree.

Add a unit test that enforces this:

```python
def test_classify_treats_naive_as_utc():
    naive = datetime(2026, 6, 1, 6, 0)         # no tzinfo
    aware = datetime(2026, 6, 1, 6, 0, tzinfo=UTC)
    assert classify_session_bucket(naive) == classify_session_bucket(aware)
```

If the dev host is not UTC, this test fails before the fix lands.

## Why prevention beats migration to Postgres

"Switch to Postgres" doesn't help retroactively: rows already stored under the bug are still wrong, and any existing classification outputs (aggregates, ML labels, paper-trading buckets) inherited the shift. After applying the defensive normalization above:

- Re-classify only — historical OHLCV / event data is fine; the bug was in interpretation, not storage.
- Re-run aggregates that grouped by bucket (event studies, daily summaries) — outputs change.
- Don't re-fetch source data — `posted_at` itself is correct UTC; only the downstream `.astimezone()` was wrong.

## Caveats

- This applies anywhere a timezone-naive datetime escapes the storage layer, not just SQLite. Same pattern: HTTP API JSON serialization stripped tz, CSV import without parsing tz, ORM with `DateTime` (no `timezone=True`) on any backend.
- The `.replace(tzinfo=UTC)` form is correct ONLY if the writer guaranteed UTC. If writers stored aware-non-UTC values that SQLite then stripped, the stored wall-clock represents a different moment and this defensive fix masks a worse bug — fix the writer first.
- pytz / dateutil have different semantics for naive datetimes than zoneinfo — the system-tz fallback behavior is a `datetime.datetime.astimezone()` property, not specific to zoneinfo.
- A dev machine in UTC (CI runners, Docker containers with `TZ=UTC`) hides this entirely. If your team has one KST/EST/JST workstation and one UTC CI box, the bug only shows up on the workstation — easy to dismiss as "works for me in CI".
