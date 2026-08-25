---
name: verify-handoff-claims-against-code-before-building
description: A delegation brief or handoff memory that says "X is missing / unsolved, go build it" is a point-in-time snapshot that may be stale. Verify the claimed-undone work actually is undone against current code/state BEFORE building — especially before destructive or large work. Skipping this risks redundant rework or destroying already-shipped value.
---

# Verify handoff/memory "undone" claims against code before building

## Problem

A multi-session delegation arrives with a confident scope: "E20-B/C/D is unbuilt (~2.2KLOC to write), and the white-space items (cross-project transfer, retract-on-ingest) are missing — go build them. First step: wipe the vault and rewrite from scratch." The brief and the linked memory both assert this state.

Acting on it directly would mean wiping a 12K-note vault and re-implementing ~2KLOC. But a 10-minute code check showed: the work was **already shipped** in a single PR merged the same day the memory was written; the vault was already healthy (288 notes, not 12K); the "missing" white-space items were either **already working** (cross-project = the vault is workspace-scoped, so products already share knowledge) or **intentionally not built** (retract-on-ingest conflicts with the founder's noise-natural-decay policy). In one session this stale-premise trap fired **twice** (the lift scope, then the white-space list).

- Symptom: a brief/memory/handoff describes work as undone, a problem as unsolved, or a metric as bad ("12K notes, all-cluster-1") — and the prescribed first action is to build/rewrite/wipe.
- Root cause: memories and briefs are **point-in-time observations**, not live state. Code keeps moving after they're written; a PR that lands the same day can leave the memory describing a pre-merge world.
- Common misunderstanding: "the delegation author just handed this to me, so their state description is current." A handoff captures the author's mental model at write time, which may predate merges, deploys, or even their own later work.

## Solution

Before building anything a brief/memory says is missing — and *always* before destructive or large work:

1. **Turn every factual claim into a check.** "12K notes" → count them. "E20-B unbuilt" → grep for the module/function. "cross-project not supported" → read where the vault root is keyed (workspace vs product). "retract not wired" → read the ingest action enum.
2. **Check git history for the claimed-missing thing.** `git log --oneline -- <path>` and `gh pr list --search` often show it shipped already, with the merge date next to the memory's write date.
3. **If reality contradicts the brief, STOP and surface it** — do not proceed on the stale premise. Report the delta (before/after table), correct the memory, and re-scope with the user. A destructive step (vault wipe, rewrite) on a stale premise destroys real value.
4. **Re-scope to what's actually left.** Usually it's a much smaller verification + polish pass, not the headline build. Here it became: dogfood-verify the shipped pipeline, then two small label/centrality quality lifts.
5. **Write the correction back into the memory** so the next session doesn't re-attempt it.

```bash
# Make the brief earn its claims:
git log --oneline -- backend/knowledge/code_graph/   # "unbuilt"? it's right there, merged 06-10
gh pr view 327 --json mergedAt,additions             # same day the "go build it" memory was written
docker exec <prod> sh -c 'find <vault>/garden -name "*.md" | wc -l'  # "12K notes"? actually 288
```

## Key Insights

- The discriminator is cheap (minutes of grep/count/git-log) and the downside of skipping it is enormous (redundant 2KLOC rewrite, or a destructive vault wipe). The asymmetry always favors verifying first.
- A memory's own metadata can betray it: when the research memo and the implementing PR share a date, the memo almost certainly predates the merge it doesn't mention.
- "Already works" hides in scoping decisions, not feature lists: cross-project transfer wasn't a missing feature — it fell out of the vault being keyed by `(region, workspace_id)` with no `product_id`. Read where the boundary is enforced, not whether a "cross-project" function exists.
- "Not built" can be "deliberately not built": absence that's consistent with a stated policy (noise-natural-decay, founder-initiated retraction) is a design choice to confirm, not a gap to fill.

## Red Flags

- A handoff/brief whose first prescribed action is **wipe / rewrite / rebuild from scratch**.
- The brief cites a dramatic metric ("12K notes", "all cluster 1", "0% coverage") as the reason to act — measure it before believing it.
- The linked memory is days/weeks old, or its write-date is suspiciously close to a relevant PR merge.
- The framing is "build the missing X" but you haven't yet grepped for X.
- You're about to delete/overwrite something you didn't create, based on someone else's description of it.

## Case: inherited numbers become fabricated evidence (2026-08-24)

The same staleness bites in a second, quieter way — not by mis-scoping the work, but by **entering
the permanent record as evidence**.

A long session was compacted; the summary carried a metric: *"the failing run produced 0
deliverables vs 2/3/10/14 historically."* That number was never re-measured. It was then quoted
into **two merged PR descriptions and a design document** as the severity argument.

Measured afterwards: the product had 48 runs; the two most recent successful ones produced **1
deliverable each**, not 2/3/10/14. The defect was entirely real (0 deliverables, 0 tool calls,
cause confirmed in code and logs) — but its **baseline had been inflated**, and the inflation now
lived in the durable artifacts.

**Why this variant is easy to miss:** a compaction summary or prior-session handoff does not *feel*
like a claim to verify. It feels like your own memory. Scope claims ("X is unbuilt") trigger
suspicion; a bare number slipped into a sentence does not.

**Rule:** the moment an inherited number is about to leave the conversation — into a PR body, a
design doc, a commit message, a report to the user — it stops being context and becomes **evidence**,
and evidence must be measured. Cheap discriminator:

```bash
# quoting "historically N per run"? count it, don't recall it
<query the actual rows, grouped by run>
```

If it is already published, correct it explicitly in the artifact rather than quietly. Related:
`activity-recording-drift-invalidates-historical-counts` (why historical counts drift even when
honestly gathered).

### Red flag (addition)

- You are about to write a comparison figure into a PR/doc that you did not measure **in this
  session**, including one that arrived via context compaction.

---

## Variant 3 — the handoff's *diagnosis* is wrong, not just its numbers (BSVibe 2026-08-25)

Both variants above are about **facts** (scope, figures). This one is about **causal claims** — the
handoff says *why* something is the way it is, and that explanation is what your whole design
inherits. It survives review because it reads as analysis, not as a claim.

Two of them, in one document, both wrong:

| Handoff said | Measured |
|---|---|
| *"`pipeline` produces values because of the founder's routing rules"* (§1.1) | The rules exist — in a workspace with **54 idle runs**. The workspace where the founder actually works (**169 runs, both products**) had **zero** rules. All 21 recorded routing decisions: `workspace_default`. |
| *"`classified_intent` is 0 rows — decide between discoverability / circularity / wrong axis"* (§3.Q2) | **None of the three.** The axis was fine (the NL compiler produced a perfect Korean intent proposal). Its enabling config table had **no writer anywhere in the product** — `upsert` had exactly one caller: a unit test. |

Had either been taken on faith, the session would have designed around a rule set that routes
nothing, and "fixed" an axis whose shape was never the problem.

**Why causal claims are the dangerous kind:** a wrong number is falsified by one query. A wrong
*explanation* is only falsified by asking "what would have to be true for this?" and then measuring
**that** — which is a step you skip precisely when the explanation sounds reasonable.

### Two cheap discriminators that caught both

```bash
# 1. Multi-tenant config: NEVER count(*) — count per tenant, then ask which tenant
#    actually does the work (runs/events), not which one has the most config.
select workspace_id, count(*) from run_routing_rules group by 1;
select workspace_id, count(*) from execution_runs group by 1;

# 2. "Feature X is unused": before theorising about WHY, check whether anything
#    can even write its enabling state.
grep -rn "\.upsert\|def set_\|INSERT INTO <table>" --include="*.py" backend/ | grep -v test
#    → callers == {a unit test} means the feature was never reachable, and every
#      behavioural explanation for its absence is post-hoc.
```

**Bonus finding from the same measurement:** the rules' `created_at` (2026-06-28) was compared
against where the founder was working *at that time* — 19 runs, all in the OTHER workspace, whose
first run came 8 days later. So the user believed they were configuring the workspace they worked
in, and the config silently landed elsewhere. **Comparing a config row's `created_at` against
contemporaneous activity** is how you tell "unused setting" from "setting saved to the wrong place".

### Red flag (addition)

- The handoff explains *why* something is broken/unused, and your plan starts from that explanation.
  Write down what must be true for it to hold, then measure that — before designing anything.
