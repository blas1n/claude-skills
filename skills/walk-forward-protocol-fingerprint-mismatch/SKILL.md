---
name: walk-forward-protocol-fingerprint-mismatch
description: When a reproduced backtest / benchmark differs from a stored result, the first hypothesis should be "did I match the execution protocol?" not "did the code regress?". Walk-forward params (train/test/step, start/end) are typically CLI args — not part of config_hash. Fingerprint via stored fold count / sample count before suspecting code or data drift.
version: 1.0.0
task_types: [measurement, debugging, reproduction]
triggers:
  - pattern: "reproducing a previous backtest / benchmark / experiment"
  - pattern: "metric drifted between two runs of the same config"
  - pattern: "suspecting yfinance / data drift / code regression after measurement disagreement"
category: trap
---

# Walk-Forward Protocol Fingerprint Mismatch

## The Pattern

You have a stored backtest result (e.g. `pr20-A-rolling2`: α +4.09%, sharpe 1.334). You re-run with what you believe is the same config and get a different result (e.g. α -4.5%, sharpe 0.97). The natural reflex is "code regressed" or "data refreshed under us". You then go diff prefetch.py, check yfinance cache mtimes, query DB for stored configs — all while missing that **the walk-forward execution protocol differs**.

`config_hash` captures algorithmic parameters (scorer type, weights, top_pct, …). It does **not** capture CLI-level execution params: `--start`, `--end`, `--train-days`, `--test-days`, `--step-days`. Two runs with byte-identical YAML can still produce different metrics because they walked different fold layouts.

## Real Example (Bloasis PR21, 2026-05-09)

PR20 stored a winner cell `pr20-A-rolling2`: α +4.09%, sharpe 1.334, 7 folds, all PASS. I built a `bloasis grid` runner and wrote a starter spec with what I believed were "PR20's params":

```yaml
walk_forward:
  start: 2022-01-01
  end: 2024-12-31     # WRONG: PR20 used 2024-10-17
  train_days: 365     # WRONG: PR20 used 180
  test_days: 120
  step_days: 120
```

Re-running the same config (rolling=2/rebal=21) gave α -4.5%, sharpe 0.97 — an 8.6pp alpha drop on the "same" config.

### What I did wrong

I went down two dead-ends before checking the protocol:

1. **"Code must have regressed in PR21's prefetch refactor"**
   - Diffed `prefetch.py` against the original inline `cli.py` block byte by byte. Identical (only difference: `window_start` moved out of for loop as micro-opt).
2. **"yfinance must have refreshed SPY data"**
   - Checked OHLCV cache mtimes, loaded SPY parquet directly, computed total return. **Same SPY file used by both runs (May 8 22:27, within TTL)**. Total return identical.

After both red herrings, I queried `acceptance_reasons_json` for the original PR20 row and saw:

```
PASS  folds: 7 >= 5
```

My grid produced `folds: 6 >= 5` and later `folds: 3 >= 5`. Same start/end can't produce different fold counts unless `train_days/test_days/step_days` differ. That was the smoking gun.

Fix: `start=2022-01-01 end=2024-10-17 train=180 test=120 step=120` → 7 folds → α +4.1% (within 0.01pp of stored).

### The fingerprint that would have saved me

`backtest_runs.acceptance_reasons_json` contained `"PASS folds: 7 >= 5"`. That `folds: 7` line is a cheap, reliable fingerprint of the walk-forward protocol. Same `start/end` + different `train_days` produces different fold counts, so checking `folds` before re-running pins down what protocol the original used.

## Why This Traps You

- **`config_hash` feels exhaustive.** It's labeled "config" so you assume it captures everything; in reality it captures algorithmic surface, not CLI-level execution context.
- **Two byte-identical YAMLs can produce different measurements** if invoked with different walk-forward CLI args.
- **Protocol differences are "silent".** Nothing crashes; both runs complete cleanly. The only signal is the metric drift itself, which gets attributed to data/code.
- **The investigation is satisfying.** Diffing prefetch.py and verifying yfinance cache mtimes feels productive — but it's looking for keys under the streetlight.
- **`config_json` in DB shows you all of YAML, but CLI args persist only as metadata** (start_date, end_date columns, sometimes nothing for train_days/test_days/step_days).

## Detection Heuristics

Before suspecting code regression or data drift on a measurement disagreement:

1. **Pull stored protocol fingerprints** — for backtest systems, that's `n_folds`, `n_trades`, `start_date`, `end_date` from `backtest_runs`, and the `folds: N >= K` line in `acceptance_reasons_json`.
2. **Compute the expected fold count from your spec** — if you can't predict it, you don't know your walk-forward params yet.
3. **If fold counts differ, stop.** It's the protocol. Don't diff code.
4. **If fold counts match but metrics still differ** — only then suspect data refresh or code regression.

## Architectural Mitigation

For new tooling: persist the full execution protocol in `backtest_runs`, not just config_hash. Specifically:

- `train_days`, `test_days`, `step_days` columns (or a single `wf_protocol_json` column).
- Or: derive a `protocol_hash` that fingerprints execution-time CLI args + config_hash together.

Either approach makes the next reproduction attempt query a single hash to know "am I running the same protocol?" without parsing acceptance reason strings.

For Bloasis specifically (as of PR21):
- `walk_forward.{start,end,train_days,test_days,step_days}` IS in grid spec YAML (good — captured in config_json for grid runs).
- Single-config `bloasis backtest` invocations don't capture train/test/step in DB. Adding three columns to `backtest_runs` would close the gap.

## Compact Decision Tree

When metric X differs between two runs you believe should match:

```
1. Pull n_folds (or equivalent sample-count fingerprint) for the original run.
2. Compute expected n_folds from your reproduction spec.
3. They differ?  → fix protocol, re-run. Done.
   They match?  → check config_json byte-equality.
4. Configs match, n_folds match, metrics still differ?
   → NOW it's data drift or code regression. Investigate.
```

The cost of step 1 is one SQL query. The cost of skipping it is hours of diffing the wrong things.
