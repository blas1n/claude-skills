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
