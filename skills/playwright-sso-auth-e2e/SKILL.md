---
name: playwright-sso-auth-e2e
description: Playwright e2e tests for SPAs with redirect-based SSO (BSVibe Auth, Auth0, Okta etc.) — page.route() cannot intercept window.location.href cross-origin navigation. Use app-side test hooks instead.
when_to_use: SPA uses external auth server (auth.bsvibe.dev, auth0.com, etc.) with redirect-based silent SSO check and Playwright e2e tests fail with "Invalid redirect_uri" or auth server JSON shown
---

# Playwright + SSO Redirect Auth E2E

## The Trap

Modern SPAs perform a "silent SSO check" on mount:

```js
// useAuth.ts pattern
useEffect(() => {
  const user = getLocalSession();
  if (user) return setToken(user.accessToken);

  // No local session → redirect to SSO server to silently check cookies
  window.location.href = `${AUTH_URL}/api/silent-check?redirect_uri=${currentUrl}`;
}, []);
```

When you write Playwright e2e tests, the page navigates to the auth server **before React mounts**, and you see:

```json
{"error":"Invalid or missing redirect_uri"}
```

instead of your app.

## What Does NOT Work

### ❌ `page.route()` cannot intercept top-level cross-origin navigation

```ts
// FAILS — page.route only intercepts same-origin fetch/XHR
await page.route("**/auth.bsvibe.dev/**", (route) => route.abort());
```

`window.location.href = "https://external-domain/..."` is a **full browser navigation**, not a request that goes through Playwright's network layer. Route handlers don't fire.

### ❌ Returning 302 redirect from `page.route` fulfill

```ts
// FAILS — causes redirect loop, networkidle never fires
await page.route("**/auth/silent-check**", (route) =>
  route.fulfill({
    status: 302,
    headers: { Location: "/?sso_error=1" },
  }),
);
```

Even if the route fires, the 302 triggers another navigation that races with `page.goto`'s response.

### ❌ Monkey-patching `Location.prototype.href` setter

```ts
// FAILS — Chromium protects native location property
await page.addInitScript(() => {
  Object.defineProperty(Location.prototype, "href", {
    set(val) { if (val.includes("auth.")) return; }
  });
});
```

Chromium blocks redefining native `Location` properties for security.

### ❌ Pre-injecting `?sso_error=1` via `history.replaceState`

```ts
// FAILS — addInitScript runs before navigation, URL is still "/"
await page.addInitScript(() => {
  const url = new URL(window.location.href);
  url.searchParams.set("sso_error", "1");
  history.replaceState(null, "", url.toString());
});
```

The init script runs in a fresh page context where the URL hasn't been set yet.

## What WORKS: App-side Test Hook

Add a `window.__E2E_SKIP_SSO__` flag check **in the auth library**:

```ts
// src/lib/bsvibe-auth/client.ts
checkSession(): User | null | 'redirect' {
  // E2E test hook: skip SSO redirect entirely
  if ((window as any).__E2E_SKIP_SSO__) return null;

  // ... normal flow
  const existing = this.getUser();
  if (existing) return existing;
  // ... redirect to SSO server
}
```

In the test fixture:

```ts
// e2e/auth.spec.ts
base.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.removeItem("bsvibe_user");  // ensure no session
    (window as any).__E2E_SKIP_SSO__ = true; // skip SSO redirect
  });

  await page.goto("/");
  // App renders LandingPage normally — no auth.bsvibe.dev navigation
});
```

For **authenticated** tests, inject a fake session matching the auth library's storage key:

```ts
const fakeUser = {
  id: "e2e", email: "e2e@test.dev",
  accessToken: fakeJwt, refreshToken: "fake",
  expiresAt: 4102444800, // year 2100
  // ... whatever fields the auth lib expects
};
await page.addInitScript((user) => {
  localStorage.setItem("bsvibe_user", JSON.stringify(user)); // exact key matters!
}, fakeUser);
```

## Critical Gotchas

### 1. localStorage key MUST match the auth library exactly

If the auth library reads `bsvibe_user` but you set `bsage_access_token`, the session is invisible and redirect fires anyway. Always grep the auth library source:

```bash
grep -n "localStorage.getItem\|localStorage.setItem" src/lib/auth/
```

### 2. Auth library migrations break fixtures

When the auth library is replaced (e.g., custom JWT → BSVibe Auth, Supabase → Auth0), the localStorage key changes. Old fixtures silently break and trigger SSO redirect.

### 3. `getByRole("heading", { name: X })` strict mode violations

Auth-related UIs often have multiple "BSage" or app-name headings (sidebar h1 + help panel h3). Use `level: 1` to disambiguate:

```ts
await expect(
  page.getByRole("heading", { name: "BSage", level: 1 })
).toBeVisible();
```

### 4. CSS-transform-hidden panels are still "visible" to Playwright

`translate-x-full` slide panels remain in the DOM with `display: block`. `toBeVisible()` returns true. Use overlay attachment or specific text content:

```ts
// Bad: panel stays in DOM
await expect(page.getByText("Help")).not.toBeVisible();

// Good: overlay backdrop is conditionally rendered
await expect(page.locator(".bg-black\\/40")).not.toBeAttached();
```

## Verification Checklist

Before debugging "auth.bsvibe.dev shows up in screenshots":

- [ ] Did the auth library's localStorage key change recently? (`git log src/lib/auth/`)
- [ ] Does the test injection key match the library's read key exactly?
- [ ] Is there an `__E2E_SKIP_SSO__` (or similar) hook in the auth library?
- [ ] Does the fake user object match the library's session shape?
- [ ] For unauthenticated tests, are you using the test hook (not `page.route`)?

## Reference

- BSage PR #14 commit `ed7492ee` — fixed 92 e2e failures with this pattern
- Playwright docs: [page.route only intercepts requests](https://playwright.dev/docs/network) — top-level navigation excluded
