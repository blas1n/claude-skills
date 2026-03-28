---
name: e2e-mock-shape-drift
description: E2E test mock fixtures using wrong API response shape — passes silently because frontend handles malformed data gracefully
version: 1.0.0
---

# E2E Mock Shape Drift

## Problem

E2E mock fixtures return a different data shape than the real API, but tests still pass because the frontend handles empty/malformed data with graceful fallbacks (empty state, loading spinner, etc.).

- 증상: All E2E tests pass, but the mock data shape doesn't match the real API. Tests are validating the empty/error state, not the feature.
- 근본 원인: Mock was written based on assumed API shape instead of checking the actual TypeScript types or backend response format
- 흔한 오해: "Tests pass, so the mocks are correct" — the frontend silently swallows the shape mismatch

## Example

```typescript
// WRONG: Nested tree format (assumed)
const MOCK_VAULT_TREE = {
  name: "vault",
  type: "directory",
  children: [
    { name: "garden", type: "directory", children: [...] }
  ],
};

// RIGHT: Flat VaultTreeEntry[] (actual API type)
const MOCK_VAULT_TREE = [
  { path: "", dirs: ["garden", "seeds"], files: [] },
  { path: "garden", dirs: [], files: ["index.md"] },
];
```

The frontend does `tree.length === 0` check → shows "Vault is empty" → test asserts tree rendered → the assertion passes because _something_ rendered, even though it's the wrong thing.

## Solution

1. **Check the actual TypeScript type** before writing mock data:
   ```bash
   grep -A 5 "export interface VaultTreeEntry" frontend/src/api/types.ts
   ```

2. **Check the API client** to see what type it expects:
   ```bash
   grep "vaultTree" frontend/src/api/client.ts
   ```

3. **Use strict assertions** in tests — not just "is visible" but check specific content:
   ```typescript
   // Weak: passes even with wrong data shape
   expect(gardenVisible).toBeTruthy();

   // Strong: verifies actual rendered content
   await expect(page.locator("text=garden")).toBeVisible();
   await expect(page.locator("text=index.md")).toBeVisible();
   ```

4. **Add a comment linking mock to type**:
   ```typescript
   // Matches VaultTreeEntry[] from src/api/types.ts
   const MOCK_VAULT_TREE_RESPONSE: VaultTreeEntry[] = [...]
   ```

## Key Insights

- Frontend resilience (graceful empty states, error boundaries) masks mock shape mismatches — the test passes, but tests the wrong codepath
- TypeScript's type system doesn't help at E2E test boundaries — the mock is just a JSON blob, not type-checked against the interface
- This is especially dangerous when API shape changes — mocks don't break, so the E2E tests give false confidence

## Red Flags

- Mock fixtures defined as plain objects without referencing the actual API type
- Tests that assert "is visible" or "is truthy" instead of checking specific content
- Mock data that looks like a different API (REST vs GraphQL conventions, nested vs flat)
- Frontend that renders an empty state without error when receiving malformed data
