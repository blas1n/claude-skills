# Playwright Selector Pitfalls & Strict Mode Fixes

## Metadata
- **Created**: 2026-03-19
- **Context**: E2E testing React SPA with Playwright
- **Trigger**: When writing Playwright E2E tests and encountering strict mode violations, text selector mismatches, or stateful button click races

## Problem

Playwright's strict mode (default) requires locators to resolve to exactly 1 element. Common text selectors silently match more than expected, causing failures that are hard to debug without screenshots.

## Pitfall 1: Substring Text Matching

`text=P1` matches **both** "P1" and "P100" (substring match is default).

```typescript
// BAD — strict mode violation
await expect(page.locator('text=P1')).toBeVisible();

// GOOD — exact match
await expect(page.getByText('P1', { exact: true })).toBeVisible();
```

Similarly, `text=default` matches "Default fallback" AND a "default" badge.

## Pitfall 2: `/` Prefix = Regex

`text=/api/v1/chat/completions` is interpreted as **regex** `api/v1/chat/completions`, not literal text.

```typescript
// BAD — treated as regex, may match unexpected elements
await expect(page.locator('text=/api/v1/chat/completions')).toBeVisible();

// GOOD — target the container element
await expect(page.locator('code:has-text("chat/completions")')).toBeVisible();
```

## Pitfall 3: Model Names in Multiple Contexts

A model name like "gpt-4o" appears in:
- Model name display (`.font-medium`)
- LiteLLM model path (`openai/gpt-4o`)
- Other models containing the substring (`gpt-4o-mini`)

```typescript
// BAD — matches 3+ elements
await expect(page.locator('text=gpt-4o')).toBeVisible();

// GOOD — scope to specific CSS class
await expect(page.locator('.font-medium:has-text("gpt-4o")').first()).toBeVisible();
```

## Pitfall 4: onBlur + 2-Click Confirmation Race

React pattern: button toggles between "Delete" and "Confirm?" via state, with `onBlur` resetting state.

```typescript
// BAD — re-locating by text can cause focus shift → onBlur fires → text reverts
await page.click('button:has-text("Delete")');
await page.click('button:has-text("Confirm?")'); // may fail!

// GOOD — use structural locator (same DOM position, immune to text change)
const row = page.locator('.divide-y > div').first();
const actionBtn = row.locator('button');
await actionBtn.click();  // Delete → Confirm?
await actionBtn.click();  // Confirm? → executes delete
```

**Why it works**: Structural locator maintains the same element reference across re-renders. No focus change = no onBlur firing.

## Pitfall 5: Conditional Rendering Assumptions

Never assume text is unconditionally rendered without reading the source:

```jsx
// Source code — only shows when > 0
{rule.conditions.length > 0 && ` · ${rule.conditions.length} condition(s)`}
```

```typescript
// BAD — assumes "0 condition(s)" is rendered
await expect(page.locator('text=0 condition(s)')).toBeVisible();

// GOOD — only test what's actually rendered
await expect(page.locator('text=1 condition(s)')).toBeVisible();
```

## Selector Strategy Priority

1. **`getByText(x, { exact: true })`** — for unique visible text
2. **CSS class scoping** — `.font-medium:has-text("x")` to disambiguate same text in different contexts
3. **Structural locators** — `page.locator('.divide-y > div').nth(0).locator('button')` for stateful elements
4. **`nth-child` on table cells** — `tbody td:nth-child(4)` for table column assertions
5. **`.first()`** — last resort when multiple matches are acceptable

## Pre-Flight Checklist

Before writing a Playwright text selector:
- [ ] Could this text appear as a **substring** of another element? → use `exact: true`
- [ ] Does the text start with `/`? → use `code:has-text()` or `getByText()` instead
- [ ] Does the button change text on click (stateful)? → use structural locator
- [ ] Is this text conditionally rendered? → verify in source code first
- [ ] Could this text appear in a sidebar/nav AND main content? → scope with `main` or CSS class
