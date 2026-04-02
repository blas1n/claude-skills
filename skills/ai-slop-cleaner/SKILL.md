---
name: ai-slop-cleaner
description: "AI-generated code cleanup — deletion-first approach, regression-safe. Removes unnecessary abstractions, verbose comments, and over-engineering."
version: 1.0.0
triggers:
  - pattern: "user asks to clean up AI-generated code, remove slop, simplify over-engineered code, or audit for unnecessary abstractions"
---

# AI Slop Cleaner

Adapted from [oh-my-claudecode](https://github.com/Yeachan-Heo/oh-my-claudecode).

## Purpose

AI-generated code accumulates "slop" — unnecessary abstractions, verbose comments, defensive code for impossible scenarios, and premature generalizations. This skill systematically identifies and removes it.

## Slop Categories

### 1. Unnecessary Abstractions
- Single-use helper functions that obscure the flow
- Abstract base classes with one implementation
- Strategy/factory patterns for 2 concrete cases
- Wrapper classes that just delegate to the wrapped object

### 2. Verbose Comments
- Comments restating the code (`# increment counter` above `counter += 1`)
- JSDoc/docstrings on obvious functions
- "TODO" comments that will never be done
- Commented-out code blocks

### 3. Defensive Over-Engineering
- Try/except catching impossible exceptions
- Null checks on values that can't be null
- Feature flags for features that shipped months ago
- Backward-compatibility shims for removed code

### 4. Premature Generalization
- Config options nobody uses
- Plugin systems with one plugin
- Generic type parameters used once
- "Utils" modules with unrelated functions

## Process

### Step 1: Audit (Read-Only)

Scan the codebase for slop patterns. Report findings:

```
## Slop Audit Results
- 12 single-use helper functions
- 8 obvious comments
- 3 unnecessary try/except blocks
- 2 abstract classes with 1 implementation

Estimated lines removable: ~200 (15% of codebase)
```

### Step 2: Prioritize

Rank by impact:
1. **High**: Abstractions that make code harder to understand
2. **Medium**: Verbose comments and dead code
3. **Low**: Minor style issues

### Step 3: Delete (with safety net)

For each deletion:
1. Identify all callers/references
2. Inline or remove the abstraction
3. Run tests to verify no regression
4. Commit atomically (one logical change per commit)

**Rule**: Delete first, add only if tests fail.

### Step 4: Verify

```bash
# Run full test suite after each batch
uv run pytest tests/ --cov=<src> --cov-fail-under=80

# Check nothing was accidentally removed
git diff --stat
```

## Anti-Patterns to Preserve

NOT slop — keep these:
- Error handling at system boundaries (API inputs, file I/O)
- Type hints on public interfaces
- Abstractions with 3+ implementations
- Comments explaining non-obvious business logic ("why", not "what")
- Configuration for deployment-varying values

## Integration

- Use after `/review` identifies code quality issues
- Complements `/simplify` (which focuses on recently changed code)
- Run before `/ship` to reduce PR diff noise
