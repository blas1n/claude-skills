---
name: single-active-resolver-degrades-on-new-account-class
description: Introducing a second CLASS of a resource (e.g. provider=executor ModelAccounts) silently breaks every resolver that assumed "exactly one active X" — they fall back to a degraded path instead of erroring, so the system still "works" but a whole feature quietly stops triggering. Audit count-based resolvers before adding a new kind.
---

# "Exactly one active X" resolvers silently degrade when you add a second class of X

## Problem

A codebase resolves a dependency with a count check like
`if len(active_accounts) != 1: return None` (then a soft/keyword fallback).
This is fine while there's only ever one active account. Then you introduce a
**second class** of that same row — same table, different `provider`/`kind`
(e.g. registering an executor worker auto-creates `provider="executor"`
ModelAccounts alongside the native LLM account). Now `len(active) == 4`, every
"exactly one" resolver returns `None`, and each silently takes its degraded
fallback.

- **Symptom**: the system still runs and ships — nothing errors — but a whole
  feature never triggers. In our case the frame-stage cheap-LLM resolver +
  settle entity extractor both bailed → weak keyword framing →
  `artifact_type_hint="direct_output"` (never `"code"`) → the `design_then_impl`
  pipeline (and the entire design→impl executor chain) never fired. The first
  dogfood "succeeded" natively on the fallback model with zero indication the
  new path was dead.
- **Root cause**: the count check conflates "how many accounts exist" with "how
  many accounts of the kind this resolver needs". Adding a sibling kind inflates
  the count.
- **Common misconception**: "I only added executor accounts, the native path is
  untouched." The native path's *resolvers* counted ALL active rows, so adding
  any sibling kind broke them — a spooky-action-at-a-distance regression with no
  diff to the native code.

## Solution

Filter by the kind the resolver actually needs BEFORE counting.

1. Grep for the assumption across the codebase, not just the obvious site:
   `len(.*accounts) != 1`, `len(.*) == 1`, `accounts\[0\]`, `\.one()`,
   `single active`, `exactly one`.
2. For each, decide which kind it needs and filter first.
3. Extract ONE shared helper so the rule lives in a single place, and point
   every site at it (we found 3 sites — one already filtered correctly, two did
   not; the inconsistency is the tell).

```python
def _single_native_account(accounts: list[ModelAccount]) -> ModelAccount | None:
    """The lone active NON-executor account, or None (zero / more than one).
    Executor (CLI) accounts can't drive a native chat model, so ignore them
    before requiring exactly one."""
    native = [a for a in accounts if a.provider != "executor"]
    return native[0] if len(native) == 1 else None
```

## Key Insights

- A count-based resolver encodes a hidden assumption: "the only rows that exist
  are the kind I want." The day a second kind lands, that assumption is false
  and the failure is **silent** (None → fallback), not loud (exception).
- The bug has **no diff in the path that breaks**. You add accounts; the frame
  resolver — untouched — starts returning None. Look for the regression at the
  *consumer of the count*, not where you made the change.
- When one resolver in a family already filters by kind (the judge LLM used
  `next(a for a in accounts if a.provider != "executor")`) and its siblings
  don't, that inconsistency is the smoking gun — copy the correct one.
- Real-data e2e is what surfaced it: unit tests seed exactly one account, so
  they pass forever. The trap only appears once a second account class actually
  coexists in a live workspace (cf. mock-fixtures-hide-wiring-bugs).

## Red Flags

- About to add a new `provider` / `kind` / `type` discriminator to an existing
  table that other code already reads.
- A feature "works in tests / the happy demo" but a downstream stage never
  fires in a freshly-provisioned-but-realistic environment.
- `if len(rows) != 1: return None` / `return <fallback>` anywhere on a hot path.
- A capability you JUST enabled (registering a worker, adding a key, seeding a
  second config) is followed by an *unrelated* feature going quiet.
