---
name: vitest-restoreallmocks-wipes-factory-mock
description: In Vitest, `vi.restoreAllMocks()` in afterEach strips the implementation from mocks created inside a `vi.mock(...)` factory (`vi.fn().mockResolvedValue([])`). The first test passes, then every later test gets `undefined` from that module — and the crash surfaces in a component section you were not even testing.
category: trap
---

# `vi.restoreAllMocks()` wipes implementations set in a `vi.mock` factory

## Problem

A component under test pulls from two API modules. You only care about one, so
you give the other a throwaway default right in the mock factory:

```tsx
vi.mock("@/lib/api/oauth-clients", () => ({
  listOAuthClients: vi.fn().mockResolvedValue([]),   // "just don't crash"
  createOAuthClient: vi.fn(),
  deleteOAuthClient: vi.fn(),
}));

vi.mock("@/lib/api/pats", () => ({ listPats: vi.fn(), createPat: vi.fn(), deletePat: vi.fn() }));

describe("...", () => {
  afterEach(() => vi.restoreAllMocks());     // routine hygiene
  ...
});
```

The factory runs **once** per module registry. `vi.restoreAllMocks()` resets
every mock's implementation, so after the first test `listOAuthClients()`
returns `undefined` forever. In the component:

```tsx
const rows = await listOAuthClients();   // undefined
setClients(rows);
...
clients.length === 0 ? ... : ...          // TypeError: Cannot read properties of undefined
```

Two things make it hard to read:

- **Test 1 passes, tests 2..n fail.** Looks like state bleeding between tests or
  a cleanup bug, not a mock-lifetime issue.
- **The error names a section you are not testing.** The component's *other*
  half throws during render, so React unmounts the tree and your query fails
  with "Unable to find an element with the text: …". The `TypeError` is buried
  above the assertion error in the output.

`vi.resetAllMocks()` and `restoreMocks: true` / `mockReset: true` in the Vitest
config have the same effect. `clearAllMocks()` does not (it only clears call
history).

## Solution

Set implementations in `beforeEach`, never in the factory — the factory is for
*shape*, `beforeEach` is for *behaviour*:

```tsx
vi.mock("@/lib/api/oauth-clients", () => ({
  listOAuthClients: vi.fn(),
  createOAuthClient: vi.fn(),
  deleteOAuthClient: vi.fn(),
}));

import { listOAuthClients } from "@/lib/api/oauth-clients";

beforeEach(() => {
  // Sibling section the component renders but this file doesn't assert on.
  vi.mocked(listOAuthClients).mockResolvedValue([]);
});
afterEach(() => vi.restoreAllMocks());
```

Leave a one-line comment saying *why* the unrelated module is stubbed —
otherwise the next reader deletes it as dead setup and reintroduces the bug.

## Diagnosis shortcut

When RTL reports "Unable to find an element with the text: X" but only from the
**second** test onward, do not start debugging the query. Grep the run output
for a thrown error first:

```bash
pnpm vitest run <file> 2>&1 | grep -E "TypeError|Cannot read properties|IntlError"
```

A render-time throw makes every subsequent query fail, so the *first* error in
the log is the real one.

## Related

- `rtl-findbyrole-empty-container-sync-query-race`
- `mock-fixtures-hide-wiring-bugs`
