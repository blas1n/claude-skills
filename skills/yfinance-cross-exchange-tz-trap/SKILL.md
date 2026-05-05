---
name: yfinance-cross-exchange-tz-trap
description: yfinance returns each symbol in its exchange's home tz (NYSE→America/New_York, ^VIX→America/Chicago, futures elsewhere). Naive tz_convert+tz_localize keeps the offset, so day N lands on different UTC times across symbols and silently breaks look-ahead invariants in cross-section pipelines.
version: 1.0.0
---

# yfinance Cross-Exchange TZ Misalignment

## Problem

`yfinance.Ticker.history()` does NOT return one consistent timezone. It returns each symbol in **its exchange's home timezone**:

| Symbol class | Exchange | yfinance tz |
|---|---|---|
| US stocks (AAPL, MSFT, JPM, SPY…) | NYSE/NASDAQ | `America/New_York` |
| `^VIX` | CBOE | `America/Chicago` |
| `^GSPC`, `^DJI`, etc. | varies | varies |
| Futures, FX, crypto | varies | varies |

**Symptom**: Single-symbol tests pass. Cross-section pipelines (panel data, market-context fetches, walk-forward backtests with VIX) silently produce wrong results, or trip a look-ahead/no-future-data invariant only when run end-to-end on real data.

**Concrete failure mode** observed in production:
```
ValueError: look-ahead in vix_series (2026-05-04 05:00:00 > 2026-05-04 04:00:00)
```
The VIX bar and the AAPL bar are for the **same trading day**, but VIX (Chicago, UTC-5 in CDT) lands on `05:00 UTC` while AAPL (NY, UTC-4 in EDT) lands on `04:00 UTC` after the obvious tz strip. The look-ahead check `vix_series.index.max() <= ts` fires false-positive.

**Root cause**: The naive normalization
```python
df.index = df.index.tz_convert("UTC").tz_localize(None)
```
preserves the wall-clock-to-UTC offset. Same calendar day → different naive timestamp depending on source exchange.

**Common misconception**:
- "yfinance is US-only, so it must return US Eastern."
- "tz_convert('UTC') aligns everything." It aligns to UTC, but the source-tz offset is now baked into the time-of-day.
- Mocks all use `pd.date_range(...)` (naive midnight) so synthetic-data tests never expose the drift.

## Solution

**After the tz strip, also `.normalize()` to floor to midnight.** Daily OHLCV bars represent a calendar date — intra-day time is meaningless and only encodes a tz offset that varies by exchange.

```python
result = df[list(OHLCV_COLUMNS)].copy()
if result.index.tz is not None:
    result.index = result.index.tz_convert("UTC").tz_localize(None)
result.index = result.index.normalize()  # ← floor to 00:00:00
result.index.name = "timestamp"
```

After this, day N is identical across every symbol regardless of source tz:

| Symbol | Raw yfinance bar | After normalize |
|---|---|---|
| AAPL (May, EDT) | `2026-05-04 00:00-04:00` | `2026-05-04 00:00:00` |
| ^VIX (May, CDT) | `2026-05-04 00:00-05:00` | `2026-05-04 00:00:00` |
| AAPL (Jan, EST) | `2024-01-02 00:00-05:00` | `2024-01-02 00:00:00` |
| ^VIX (Jan, CST) | `2024-01-02 00:00-06:00` | `2024-01-02 00:00:00` |

## Regression test

A regression test must use a **non-NYSE source tz** — otherwise it tautologically passes:

```python
def test_ohlcv_floors_index_to_midnight_for_cross_exchange_alignment() -> None:
    chicago_idx = pd.DatetimeIndex(
        pd.date_range("2024-05-04", periods=3, freq="D", tz="America/Chicago"),
        name="Date",
    )
    df = pd.DataFrame({...}, index=chicago_idx)
    with _patch_yfinance(df):
        out = YfOhlcvFetcher().fetch("^VIX", date(2024, 5, 4), date(2024, 5, 6))
    assert out.index.tz is None
    assert (out.index == out.index.normalize()).all()
    assert out.index[0] == pd.Timestamp("2024-05-04")
```

## Detection: how to find this in an existing codebase

```bash
# Anywhere a yfinance fetcher returns a DataFrame and downstream code compares
# indexes across symbols (panel data, look-ahead checks, cross-section z-scores).
rg -l "yf\.Ticker|yfinance" --type py
rg "index\.max\(\)|index\.min\(\)" --type py
```

If you see `vix_series.index.max() > ts` or `pd.concat([df_a, df_b], axis=1)` across symbols pulled from yfinance, the trap is live.

## Key Insights

- **yfinance source tz is symbol-dependent, not user-controlled.** No `tz=` kwarg fixes this at fetch time. Normalize at the boundary.
- **Daily bars are dates, not timestamps.** Treating them as timestamps imports the source-system's tz politics into your application. `.normalize()` is the cleaner abstraction.
- **Synthetic mocks hide the bug.** Every mock in this codebase used `pd.date_range(start, end)` which is naive midnight. The 381 tests passing on synthetic data taught us nothing about the production shape. **Run live CLI commands end-to-end at least once before merging fetcher changes.**
- The fix is one line. The bug is invisible until cross-symbol or live data is involved.

## Red Flags

Suspect this trap when:

- Walk-forward / panel-data backtest passes on synthetic data, fails or behaves weirdly on real data
- `look-ahead` / `index.max()` invariants trip with timestamps that differ by exactly **1 hour** (NYSE↔CBOE) or **2–3 hours** (NYSE↔futures/Asia)
- Cross-section operations (`pd.concat(axis=1)`, joins on date) silently drop rows or produce duplicates near day boundaries
- Test mocks use `pd.date_range(...)` without a `tz=` argument — they encode the assumption that yfinance returns naive data, which is wrong
- Different symbols' last-bar timestamps disagree even though they should both be "today's close"

## Adjacent traps (worth a glance if you hit this)

- **Mocking yfinance via `patch.dict("sys.modules", {"yfinance": MagicMock()})`** can trigger `pyarrow.lib.ArrowKeyError: A type extension with name pandas.period already defined` when a later test in the same file writes parquet. Patch the fetcher's `_download` static method directly instead.
- **`auto_adjust=False`** (the typical default for "I want unadjusted Close") means split/dividend day price jumps will hit your momentum / volatility features as legitimate ~7–10x moves. Either set `auto_adjust=True` or pre-process for splits.
