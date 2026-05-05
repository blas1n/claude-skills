---
name: sdk-fetch-closure-monkey-patch-trap
description: "API SDKs that capture window.fetch at module-init time can't be intercepted by later monkey-patching. Use Playwright page.route() / MSW for tests; use the SDK's own override hook in app code."
version: 1.0.0
triggers:
  - pattern: "Playwright/Cypress browser_evaluate fetch monkey-patch lands but app SDK calls still hit the real network, or visual tests show empty state when mocks were 'installed'"
category: trap
---

# SDK fetch-closure monkey-patch trap

## Symptom

You install a `window.fetch` monkey-patch via Playwright's
`browser_evaluate` (or any post-load script) so a visual test can
load with mock data. Direct `fetch()` calls in the same browser
context return the mock — but the app's own `api.something()` calls
still hit the real backend (returning 401, 404, CORS errors, etc.)
and the page shows the empty state.

## Why

API SDKs frequently capture `fetch` (or any global) **at module
init time** for performance and safety:

```ts
// inside @some/api package
import { fetch as builtinFetch } from "./isomorphic-fetch";

// Closure-captured. Setting window.fetch later won't affect this.
const _fetch = builtinFetch;

export const apiClient = {
  async request(path: string) {
    const r = await _fetch(BASE + path);  // uses _fetch, not window.fetch
    ...
  },
};
```

Common culprits we've hit:

- `@bsvibe/api`'s `createApiFetch`
- `axios` (it has its own adapter abstraction; `axios.defaults` is the
  override knob, not `fetch`)
- `ky`, `wretch`, `redaxios` — same pattern
- Any wrapper that does `const fetch = globalThis.fetch.bind(globalThis)`
  at module load

If the wrapper does `globalThis.fetch(...)` at call time it WILL
pick up your patch — but most don't, for stability reasons.

## Diagnosis

Two-line check inside the page:

```ts
// Direct fetch — uses your patched window.fetch
await fetch("/api/foo");          // → mock response

// SDK call — uses its closure-captured reference
await api.foo();                  // → real network
```

If the first returns mock and the second hits the network, you've
got the closure trap.

## Fix

**For test code: use the test framework's transport-layer mock,
not in-page monkey-patching.**

- Playwright: `page.route("**/api/foo", route => route.fulfill({...}))`
  — intercepts at the network layer before any JS runs, immune to
  closure captures. This is what `e2e/fixtures/index.ts` should
  install for every API the app uses.
- MSW (`msw/browser`): intercepts fetch + XHR via service worker.
- Cypress: `cy.intercept(...)`.

Why these work: they hook below the JS layer. The SDK's `_fetch`
reference still points to the original function, but when that
function actually fires a request, the test framework intercepts
the network call.

**For app code: use the SDK's documented override hook.**

If the SDK exposes `setFetch(custom)` or a `fetchImpl` constructor
option, use that. Don't try to monkey-patch around it.

## Real-world: writing a Playwright spec for a graph view

```ts
import { test, expect } from "./fixtures";

const N = 60;
const nodes = /* generate */;
const links = /* generate */;
const communities = /* generate */;

test("desktop with data", async ({ page }) => {
  await page.route("**/api/vault/graph", (r) =>
    r.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ nodes, links, truncated: false }),
    }),
  );
  await page.route("**/api/vault/communities**", (r) =>
    r.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(communities),
    }),
  );

  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/#/graph");
  await page.waitForSelector("canvas");
  await page.waitForTimeout(2500); // let force-graph settle
  await page.screenshot({ path: "test-results/visual/graph.png" });
});
```

`page.route` runs before any app code, so it doesn't matter what
the SDK captured during init. Mocks work consistently.

## Adjacent trap: inner-scroll vs page-scroll for screenshots

When `page.screenshot({ fullPage: true })` returns the same image
as the viewport-only call, the captured area has its own
`overflow-y-auto` container. `fullPage` and page-level
`scrollIntoViewIfNeeded()` only operate on the document scroller.

Drive the inner ancestor directly:

```ts
const heading = page.locator("text=MCP Server").first();
await heading.waitFor();
await heading.evaluate((el) => el.scrollIntoView({ block: "start" }));
await page.waitForTimeout(300);
await page.screenshot({ path: "..." });
```

Same idea: the abstraction (here `fullPage`, in the main trap
`window.fetch`) doesn't reach the layer where the actual state
lives. Push the operation down to that layer.
