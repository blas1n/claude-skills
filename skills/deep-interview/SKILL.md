---
name: deep-interview
description: "Requirements clarification through Socratic questioning with mathematical ambiguity scoring. Prevents 'that's not what I meant' outcomes."
version: 1.0.0
triggers:
  - pattern: "user provides vague requirements, ambiguous feature request, or complex task with multiple possible interpretations"
---

# Deep Interview — Requirements Crystallization

Adapted from [oh-my-claudecode](https://github.com/Yeachan-Heo/oh-my-claudecode).

## Purpose

Before writing any code, systematically eliminate ambiguity in requirements through structured questioning. Only proceed when ambiguity score drops below 20%.

## Process

### Phase 1: Initial Analysis

Read the user's request and identify:
1. **Explicit requirements** — what they clearly stated
2. **Implicit assumptions** — what they likely mean but didn't say
3. **Ambiguous areas** — where multiple valid interpretations exist
4. **Missing information** — what's needed but not provided

### Phase 2: Ambiguity Scoring

Score each requirement dimension 0-100% ambiguity:

| Dimension | Score | Notes |
|-----------|-------|-------|
| Scope | ?% | What's included/excluded |
| Behavior | ?% | Expected input/output |
| Edge cases | ?% | Error handling, limits |
| Integration | ?% | How it connects to existing code |
| Performance | ?% | Speed, memory, scale requirements |

**Overall ambiguity** = weighted average. Threshold: **< 20% to proceed**.

### Phase 3: Socratic Questioning

For each high-ambiguity dimension, ask targeted questions:

- **Not**: "What should happen?" (too open)
- **Instead**: "When X happens, should the system do A or B? Here's why it matters: [consequence]"

Present **concrete alternatives** with tradeoffs, not open-ended questions. Maximum 3-4 questions per round.

### Phase 4: Confirmation

Summarize the crystallized requirements:

```
## Confirmed Requirements
1. [Specific, testable requirement]
2. [Specific, testable requirement]

## Decided Tradeoffs
- Chose A over B because [reason]

## Out of Scope (explicitly)
- [Thing that won't be done]

## Remaining Ambiguity: X% (proceed/ask more)
```

## When to Use

- Complex feature requests with multiple valid interpretations
- Bug reports where root cause is unclear
- Refactoring requests where scope isn't defined
- Any task where getting it wrong wastes significant effort

## When NOT to Use

- Clear, specific requests ("add a field X to model Y")
- Bug with obvious reproduction steps
- Tasks the user has already thoroughly specified

## Integration with Other Skills

After deep-interview completes with < 20% ambiguity:
- → `/writing-plans` to design implementation
- → `/feature-workflow` to start TDD cycle
- → `/office-hours` if the idea itself needs validation first
