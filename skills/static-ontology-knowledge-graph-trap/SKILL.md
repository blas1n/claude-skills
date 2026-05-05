---
name: static-ontology-knowledge-graph-trap
description: "Hard-coded note_type / category enums in a knowledge system create filing cabinets, not knowledge graphs. The trap: classification looks like success (notes neatly distributed across folders) while the actual graph value (emergent connections, surprising links) stays at zero. Static ontology + LLM classifier = sophisticated tagger, not graph thinking."
version: 1.0.0
category: trap
---

# Static Ontology Trap in LLM-Backed Knowledge Systems

## When to Use

Designing or reviewing any system that:
- Stores user knowledge (notes, memories, conversations, documents)
- Uses an LLM to classify/organize/structure that input
- Has a fixed enum of categories (`note_type`, `kind`, `category`) baked into:
  - Folder structure (`facts/`, `insights/`, `projects/`)
  - Frontmatter / metadata (`type: fact`)
  - LLM prompts (`pick one of: idea, insight, project, ...`)
  - Database schemas / types
  - Frontend filters / colors

If yes — you're building a filing cabinet that LARP's as a knowledge graph. The enum is the trap.

## The Symptom Pattern

You build the system. You demo it:
- Import 30 mixed notes
- LLM cleanly puts them into 8 folders
- Demo report says "✓ 30 notes classified, 7 insights / 5 facts / 10 projects / ..."
- Looks like success

But:
- User asks "show me what connects to [[Authentication]]" → no useful answer
- User finds same concept duplicated across 5 folders
- Cross-references between notes are limited to wikilinks the LLM happened to place IN-batch
- After 6 months: 1000 notes in neat folders, zero emergent insight
- User feedback: "I expected this to find connections I didn't know about. It just files things."

You optimized the wrong metric. Classification accuracy is not graph value.

## Why It's Silent

1. **Classification is observable, discovery isn't.** You can write a test for "did this note get the `project` type?". You cannot easily test "did the system surface a non-obvious connection?". The visible metric drives the design.

2. **LLM compliance feels like intelligence.** Forcing the LLM to "pick from this enum" returns 100% valid answers (it's good at constrained generation). The illusion of correctness hides the lack of original output.

3. **Folders feel safe.** "Where are my facts?" → `facts/` directory. Browsable, intuitive, traditional. The org chart of knowledge feels right because it mirrors filesystems.

4. **Enum is a one-line addition that becomes a 50-file dependency.** Once `note_type` is in the schema, the prompt, the folder structure, the UI filter, the API query params, the graph view's color legend — pulling it out means touching all of them.

## Why Filing Cabinet ≠ Knowledge Graph

| Filing cabinet | Knowledge graph |
|---|---|
| Identity = `type: X` (metadata field) | Identity = position in graph (what it connects to) |
| Type chosen from fixed enum | Type emerges from clusters / communities |
| Folders by type (`facts/`, `projects/`) | Flat or chronological storage |
| Browsing: "show me all facts" | Querying: "what links to X" / "what bridges A and B" |
| Static — type doesn't change | Dynamic — meaning shifts as edges accumulate |
| LLM does classification | LLM does extraction (entities, relations) and discovery |

## Diagnostic Questions

Ask these about the system you're designing or reviewing:

1. **What are the success metrics for "the system worked"?**
   - If: "every input got categorized" → filing cabinet
   - If: "the user found a connection they didn't know about" → graph

2. **Where is `type` (or its synonym) defined?**
   - If: a Python enum / TypeScript union / database CHECK constraint → static
   - If: as nodes in the graph that the user can rename/merge/split → dynamic

3. **Could you delete the enum and the system still organize content?**
   - If no: the enum is structural, you're filing
   - If yes (clusters, tags, graph traversal still work): you're graphing

4. **What does the LLM prompt ask?**
   - "Pick one of: idea, insight, project, ..." → classifier
   - "What is this about? What does it connect to? What entities does it mention?" → extractor

5. **What happens when the user dumps in 30 unrelated docs?**
   - 30 notes in 8 folders, neatly sorted → filing cabinet (test report looks great)
   - 30 notes + emergent communities + unexpected cross-links surfaced → graph

If 4+ of 5 say "filing cabinet", the system has the trap.

## How To Avoid

### Design-time defenses

1. **Don't make `type` (or `category`, `kind`) a primary field.** Demote it to one of many tags from day one. If you need typed views, derive them from tag queries.

2. **Folder structure should not encode taxonomy.** Use date (`notes/2026-05/`), hash (`notes/ab/cd/`), or single flat directory. Reserve folders for substantive splits (raw vs. compiled, e.g. `seeds/` vs `garden/`).

3. **LLM prompt asks for extraction, not selection.** "What entities are mentioned? What concepts? What does this connect to?" — open-ended. Not "which of these 8 buckets does this go in?"

4. **Build the graph extractor BEFORE the type system.** If you know which entities are in each note and how they relate, "type" is post-hoc analytics, not a primary axis.

### Refactoring an existing trap

If you've already shipped a filing cabinet:

1. **Stop new damage first.** Make `type` field optional in writes. New entries can omit it.
2. **Add the graph layer alongside.** Build entity extraction + relation graph in parallel. Don't break the existing folders.
3. **Migrate frontend.** Replace type-coloring with community-coloring. Replace type-filter with tag/entity-filter.
4. **Migrate vault structure.** Move `garden/insights/X.md` → `garden/notes/YYYY-MM/X.md` with `tags: [..., insight]` preserving the old type as a tag.
5. **Delete the enum.** Only after 1-4 land. Otherwise the dependencies will pull you back.

This is multi-PR, multi-week. Plan for it.

## Real-World Cases

- **BSage (2026-05)**: 8 hardcoded note_types → discovered via user pushback after a demo report claimed "32 notes classified successfully across 7 type folders". Users didn't get value because no cross-cluster discovery happened. Refactor delegated to `~/Docs/BSage_Dynamic_Ontology_Refactor.md` (5 phases, ~5 weeks).

- **Roam Research's design choice**: zero types, only tags + backlinks + queries. Created the modern thinking on emergent ontology. Notion later added databases/types and is structurally a filing cabinet despite sharing some surface (backlinks) with Roam.

## Cost of Missing This

You will:
1. Ship a system that demos well ("look, perfect classification")
2. Get user feedback "I thought this would help me see patterns"
3. Realize you need 5 weeks of architectural refactor to fix the foundational design choice
4. Pay the cost of migrating live user vaults

Recognizing the trap during design = days of work. Recognizing it after shipping = weeks plus user disruption.

## Related

- Karpathy Wiki philosophy (continuous self-organization, LLM as merger not classifier)
- `large-codebase-deprecation-removal` — relevant when refactoring out of the trap
