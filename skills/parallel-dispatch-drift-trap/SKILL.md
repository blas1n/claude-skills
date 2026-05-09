---
name: parallel-dispatch-drift-trap
description: When two code paths (backtest vs live, dev vs prod, sync vs async, primary vs fallback) need the same `if cfg.type == X` dispatch but each owns its own copy, every new type added to one path silently uses a stale default in the other. The system "works" in both paths — just produces different behavior. Detect by: any new branch added to a config-driven dispatch warrants a grep for every other place that reads the same config field.
version: 1.0.0
task_types: [implementation, refactoring, debugging]
triggers:
  - pattern: "adding a new value to a config Literal / enum / scorer type / strategy type"
  - pattern: "two pipelines (backtest vs live, paper vs real, dev vs prod) that should produce equivalent behavior"
  - pattern: "user reports the production / live / paper path silently behaves differently from the test / backtest path"
category: trap
---

# Parallel Dispatch Drift Trap

## The Pattern

You have a config field — `cfg.scorer.type`, `cfg.broker.kind`, `Settings.queue_backend`, whatever — that drives an `if/elif` dispatch to instantiate the right implementation. The dispatch lives in one well-tested code path. Months later, a parallel code path needs the same behavior — live trade vs backtest, paper vs real, dev vs prod, sync vs async.

Instead of factoring the dispatch out, the parallel path inlines its own "good enough" version: hardcoded default, or a partial copy of the dispatch as it existed at the time. From then on, every new type added to the first path's dispatch silently falls back to the parallel path's default. **Both paths still "work"** — no exceptions, no warnings, no obvious failure. They just produce different behavior, and the drift is invisible until something downstream is measured against expectation.

## Real Example (Bloasis PR48, 2026-05-10)

`Backtester._build_scorer` had a 9-way dispatch on `cfg.scorer.type` — RuleBasedScorer, JTMomentum, PEAD, EDGARTextDiff, IntersectScorer, etc. Each scorer was added one at a time over many PRs.

`_build_live_candidates` (the function `bloasis trade paper` calls to produce candidates from yfinance prices) was written when only RuleBasedScorer existed. It hardcoded:

```python
scorer = RuleBasedScorer(cfg.scorer)
scored = [scorer.score(fv, cv_by_sym[fv.symbol]) for fv in feature_vectors]
```

Every subsequent scorer (JT, PEAD, EDGAR, fundamental_llm, intersects) was added to backtester's dispatch but never to the live path. Backtest measurements treated `cfg.scorer.type = "edgar_textdiff"` correctly; paper trading silently used RuleBasedScorer regardless of config.

### How it surfaced

Smoke test: `bloasis trade paper -c configs/edgar-rolling2.yaml -s ...` — expected ~2 BUY orders (top decile of 20 symbols). Got **zero orders**.

Investigation:
- yfinance fetch: succeeded
- Account access: succeeded
- Order submission: never invoked

After tracing, found `_build_live_candidates` hardcoding RuleBasedScorer. EDGAR scorer's per-symbol `score()` returns a 0.5 placeholder (the real logic is in `score_cross_section`, which the live path also wasn't using). RuleBasedScorer treated the FeatureVectors as best-it-could and produced scores below entry_threshold, so SignalGenerator emitted zero BUYs.

### What CLAUDE.md said vs what was true

The codebase had architectural rules saying "same scoring layer in live and backtest paths." That was true at the *interface* level — `Scorer.score()` is the same protocol. But the **dispatch** that selects which scorer to instantiate was duplicated. The rule didn't prevent the trap.

### Fix

1. Extract `Backtester._build_scorer` to a shared `bloasis.scoring.factory.build_scorer(cfg) -> Scorer`. Single source of truth for the type → scorer mapping.
2. Both backtester and live path call the factory.
3. Live path also delegates feature-vector building to `Backtester._build_candidates(date, scorer)` so the cross-section scoring step is shared too.

After: `bloasis trade paper -c configs/edgar-rolling2.yaml` produced AMZN BUY (score 0.99) — first real EDGAR-driven paper order.

## Why This Traps You

- **Both paths "work"** — no exception, no log warning. The fallback is silent. The only signal is the *outcome* differing from expectation, and only if you measure.
- **Tests don't catch it.** The unit tests for the dispatch in path A pass. The unit tests for path B pass with mocked scorers. Nothing exercises both real paths against the same config.
- **Documentation lies by omission.** "Same scoring runs in live and backtest" is true at the protocol level; the dispatch glue isn't part of the protocol so the rule doesn't constrain it.
- **Adding new types feels safe.** You added a branch to the dispatch you can see. The other branch you can't see — because it's a hardcoded default in another file — quietly uses the wrong implementation.
- **Drift is monotonic.** Every new type widens the gap. By the time someone notices, half the configs map to the wrong implementation in the secondary path.

## Detection Heuristics

When adding a new branch to a config-driven dispatch (`if cfg.X.type == ...`):

1. **Grep for the dispatch field.** `rg 'cfg\.X\.type ==' src/` will find every consumer. Each one needs the new branch or a documented "this consumer doesn't care."
2. **Grep for the type's primary class.** If you added `pead_jt_intersect` mapping to `IntersectScorer(JTMomentumScorer, PEADScorer)`, grep for `IntersectScorer(`. If only the dispatch site instantiates it, you missed nothing. If something else does, that's a parallel path.
3. **Look for hardcoded defaults that resemble the dispatch's first branch.** `RuleBasedScorer(cfg.scorer)` outside the dispatch is a smell — that's almost certainly a parallel-path stub waiting to drift.

## Architectural Mitigation

Once you spot a parallel-dispatch trap, the fix is structural, not local:

- **Extract the dispatch to a factory function** with a single, well-named public API. `build_X(cfg) -> X`. Both paths call the factory.
- **Make the dispatch return type a Protocol/ABC.** Both paths consume the same interface. Adding a new type means adding to the factory and (if needed) extending the Protocol — both visible in one place.
- **If the parallel path also needs other shared logic** (in our case: cross-section scoring, EDGAR prefetch), extract that too. Otherwise the next "same dispatch, different implementation" trap is one PR away.
- **Add a regression test that runs both paths against the same config** and asserts they produce equivalent outputs. Mocked is fine — the test is verifying the dispatch path, not the math.

## Related skills

- `freeform-config-dict-grep-all-consumers` — same family. Untyped config keys spread to multiple readers; adding a new key only to one reader silently breaks others. The fix here (extract a typed factory) is one resolution.
- `library-fix-doesnt-cascade-when-callers-rewrap` — different mechanism (calling code wraps results), same shape (one fix, multiple call sites silently miss it).

## Compact decision tree

When you're about to add a new value to a config Literal / enum / type:

```
1. grep for all readers of cfg.X.type
2. multiple readers? → factory missing. fix that first.
3. single reader? → safe. add the branch.
```

When you're debugging a "live/paper/prod path doesn't seem to use the right implementation":

```
1. grep for cfg.X.type usage in the pipeline that's misbehaving
2. found hardcoded default? → that's the trap. extract a factory.
3. found dispatch that looks shorter than the primary path's? → parallel-dispatch drift. extract a factory.
```
