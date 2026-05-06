---
name: survey-existing-abstractions-before-design-spec
description: When designing new layer/feature spec for an established codebase, survey existing ABCs/Protocols/dual-impl patterns BEFORE locking spec invariants. Skip the survey and you'll invent parallel abstractions that need rework.
---

# Survey existing abstractions before design spec

## Problem

When designing a new feature/layer for a non-trivial codebase, the natural first reflex is to **draft from first principles**: identify the new domain, sketch new ABCs, lock invariants, only then look at existing code.

This produces parallel abstractions. The codebase often already has ~60–80% of the supporting infrastructure (storage backends, index protocols, scheduler, lock primitives, approval interfaces, event bus, deployment-aware dual-impls). Designing without first checking forces ping-pong rework once existing patterns are discovered.

- Symptom: spec ping-pong rounds about abstraction shape (lock vs queue, in-process vs distributed, ABC vs concrete) → user prompts to "check the existing codebase" → discover 70% already exists → spec gets simpler / smaller in retrospect
- Root cause: design-first-explore-later inversion in cognitively expensive sessions
- Common misunderstanding: "I'll explore existing code only if I need to integrate" — but the codebase's existing ABC *shape* should constrain new spec from the start

The trap is especially acute for codebases with mature **dual-deployment-mode** ABCs (self-host + SaaS / cloud), because new layers in such codebases SHOULD mirror the established dual-impl pattern. Independent design produces awkward grafts.

## Solution

Before drafting any spec section that introduces new abstractions:

1. **Map the package surface**:
   ```bash
   ls <pkg>/<core-area>/
   ls <pkg>/<adjacent-areas>/
   ```
   Note module names — they hint at existing concerns.

2. **Find existing ABCs/Protocols**:
   ```bash
   grep -rn "class.*ABC\|Protocol\|abstractmethod" <pkg>/ | head -40
   ```
   Each is a candidate template or direct reuse.

3. **Find existing dual-impls** (the strongest signal):
   ```bash
   # If a codebase has Foo ABC with FooLocal / FooCloud impls already,
   # any new "self-host vs SaaS" abstraction MUST mirror this pattern.
   grep -rn "class.*ABC" <pkg>/ -A 2
   ```
   Read the ABC method list. If your new abstraction has 60%+ overlap, use the existing one.

4. **Find existing infra you'd otherwise reinvent**:
   - Scheduler / cron framework → don't write new cron
   - Write queue / write lock → don't write new mutation lock primitive without checking
   - Event bus / event types → extend existing enum, don't introduce parallel
   - Approval / Safe Mode → extend existing surface
   - Embedder / vector store → reuse
   - Confidence / decay model → reuse the math, don't reinvent
   - Frontmatter / markdown helpers → critical reuse target
   - Config / settings → use existing pydantic-settings, don't add layer

5. **Build the Reuse Map BEFORE the spec body**:

   | Existing module | API | Used by |
   |---|---|---|
   | `pkg/storage.py:StorageBackend` | read/write/list | every vault write |
   | `pkg/scheduler.py:Scheduler` | cron registration | new lint plugin |
   | `pkg/safe_mode.py:SafeModeGuard` | approval gate | mutation pipeline |
   | ... | ... | ... |

   This goes at the TOP of the design spec, not as an afterthought.

6. **Only after step 5, draft new abstractions**:
   - For each new ABC, justify why an existing ABC doesn't cover it
   - For each new module, list which existing modules it reuses
   - Net new code estimate AFTER reuse subtraction

7. **Explicit non-reuse rationale** is also valuable:
   - Some existing infra LOOKS reusable but shouldn't be (e.g., audit_outbox is parallel concern when vault is SoT)
   - Document the explicit non-reuse to prevent future confusion

## Key Insights

- The codebase's existing ABC *shape* should constrain new spec from the start — not be discovered after spec ping-pong.
- Mature codebases with dual-deployment-mode ABCs (self-host vs cloud) have already solved abstraction shape questions. New layers must mirror, not parallel-design.
- The "Reuse Map" is the deliverable that prevents reinvention — make it a first-class spec section, not an appendix.
- Specific high-value reuse targets in any mature codebase: storage backend, event bus, scheduler, approval/Safe Mode, frontmatter helpers, config. These are nearly always already present in production-grade codebases.
- When user prompts "check the existing codebase" mid-spec, that's the signal that step 1–5 above were skipped. Treat as a recoverable warning, not a sunk cost.

## Red Flags

Suspect this trap when:

- About to introduce an ABC + dual impl (in-memory vs DB-backed, in-process vs distributed) in a codebase you haven't grepped for existing ABCs
- About to write a "MutationLock" / "WriteQueue" / "Scheduler" / "EventBus" / "ApprovalInterface" / "StorageBackend" — these are commonly already present
- Spec has been ping-ponging for >2 rounds on abstraction shape decisions
- About to lock spec invariants without having read any of `<pkg>/<core>/__init__.py`, `<pkg>/<core>/storage.py`, `<pkg>/<core>/events.py`, `<pkg>/<core>/scheduler.py`, or equivalents
- User says "확인해봐 / check the codebase / 코드베이스 파악해줘" mid-design — that's the signal the survey was skipped

## Concrete trigger checklist

For Python codebases specifically:

```bash
# Before any spec session that introduces abstractions for an existing codebase:
ls <pkg>/<area>/
grep -rln "class.*ABC\|Protocol\|abstractmethod" <pkg>/ | head -20
grep -rn "class.*Backend\|class.*Store\|class.*Manager\|class.*Scheduler" <pkg>/ | head -20
cat <pkg>/<core>/__init__.py
cat <pkg>/core/config.py | grep -E "^\s+\w+:\s+\w+\s+="  # settings shape
```

5 minutes of this → save 2+ hours of spec ping-pong.

## Real example (BSage canonicalization, 2026-05-06)

Designed `CanonicalizationIndex` ABC + `InMemoryCanonicalizationIndex` + `PostgresCanonicalizationIndex` (deferred) without checking codebase. Multiple ping-pong rounds on lock vs queue, processor vs handler-executor, watcher implementation. After user prompted codebase survey, discovered:

- `bsage/garden/storage.py:StorageBackend` ABC + `FileSystemStorage` impl already existed (was about to "extract VaultBackend abstraction" as if new)
- `bsage/garden/graph_backend.py:GraphBackend` ABC + `VaultBackend` (NetworkX) + `GraphStore` (SQLite) was the **exact dual-impl template** being independently sketched
- `bsage/core/scheduler.py:Scheduler`, `bsage/core/safe_mode.py:SafeModeGuard`, `bsage/garden/confidence.py:decay_factor`, `bsage/garden/embedder.py:Embedder`, `bsage/garden/markdown_utils.py`, `bsage/core/events.py:EventBus + EventType` — all directly reusable as-is
- `bsage/garden/vault_linter.py:VaultLinter`, `bsage/garden/migrations.py:plan_flatten`, `bsage/garden/index_subscriber.py` — pattern templates
- ~70% of supporting infrastructure already existed; ~3,000–4,000 LoC genuinely new vs original sketch of 5,000+ LoC

Had the survey come first, the spec would have:
- Started from "we mirror existing GraphBackend pattern for CanonicalizationIndex"
- Mentioned "use existing Scheduler/SafeModeGuard/Embedder/decay model" upfront
- Cut multiple ping-pong rounds about abstraction shape

The lesson is captured in `Class_Diagram.md §10 Reuse Map` — that section should have been written FIRST, not last.
