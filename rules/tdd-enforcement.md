# TDD Enforcement

## CRITICAL: Mandatory TDD for All Implementation Work

**Before writing ANY production code** (new feature, bug fix, refactoring, behavior change), you MUST:

1. Invoke the `/feature-workflow` skill FIRST (TDD + E2E 통합 워크플로우)
2. Follow the Red-Green-Refactor cycle exactly as the skill instructs
3. Write E2E tests/checklist alongside unit tests
4. NEVER write implementation code before a failing test exists

This applies to ALL projects, ALL languages, ALL contexts.

**No exceptions. No rationalizations. No "just this once".**

### Auto-Trigger Conditions

Invoke `/feature-workflow` automatically when:
- User asks to implement a feature
- User asks to fix a bug
- User asks to add/change behavior
- User asks to refactor code
- Any task that will result in new or modified production code

### NOT Required For

- Configuration changes (pyproject.toml, settings files)
- Documentation-only changes
- Dependency updates
- Pure research/exploration (no code changes)
