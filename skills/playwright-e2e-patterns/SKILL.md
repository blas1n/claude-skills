---
name: playwright-e2e-patterns
description: "Playwright E2E patterns — devcontainer setup (fonts, system libs), selector pitfalls, API-based testing"
version: 1.0.0
triggers:
  - pattern: "writing Playwright E2E tests, elements report hidden in Docker, or strict mode selector violations"
---

# Playwright E2E Patterns

## 1. Devcontainer Environment Setup

### Missing Fonts = All Text "Hidden"
Minimal Docker images have zero fonts. Chromium can't render text → zero dimensions → `toBeVisible()` fails on ALL text.

**Diagnosis**: `fc-list` returns empty.

**Fix (Dockerfile)**:
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core fontconfig && rm -rf /var/lib/apt/lists/*
```

**Fix (no root)**: Install via micromamba:
```bash
export MAMBA_ROOT_PREFIX=$HOME/.mamba
micromamba create -n pw-deps -c conda-forge -y fonts-conda-forge font-ttf-dejavu-sans-mono fontconfig
mkdir -p ~/.fonts && ln -sf $MAMBA_ROOT_PREFIX/envs/pw-deps/fonts/* ~/.fonts/
```

Set in `playwright.config.ts`:
```typescript
use: {
  launchOptions: {
    env: {
      ...process.env,
      FONTCONFIG_PATH: resolve(homedir(), '.config/fontconfig'),
      FONTCONFIG_FILE: resolve(homedir(), '.config/fontconfig/fonts.conf'),
    },
  },
},
```

### Missing System Libraries
Chromium needs `libnss3`, `libgbm`, etc. For libs not in conda-forge, create minimal stub `.so` files.

---

## 1b. Auth Mock with Custom Auth SDKs

### Problem: `addInitScript` sets wrong localStorage key

Custom auth SDKs (e.g., BSVibeAuth) use their own localStorage keys — NOT the ones you'd guess.

**Symptom**: Page redirects to external auth server (e.g., `auth.bsvibe.dev/api/silent-check`) despite mock setup. Screenshot shows auth error JSON instead of app UI.

**Root cause**: `injectAuth` stored tokens under app-specific keys (`bsnexus_access_token`), but the auth SDK reads from its own key (`bsvibe_user`).

**Fix**: Read the SDK source to find the exact key and expected shape.
```typescript
// ❌ Wrong — guessing the key name
localStorage.setItem('myapp_access_token', 'mock-token')

// ✅ Right — match the SDK's actual storage key + full object shape
const bsvibeUser = {
  id: 'user-001', email: 'dev@test.dev', tenantId: 'tenant-001',
  role: 'authenticated', accessToken: 'mock-token',
  refreshToken: 'mock-refresh', expiresAt: Math.floor(Date.now() / 1000) + 3600,
}
localStorage.setItem('bsvibe_user', JSON.stringify(bsvibeUser))
```

**Diagnosis**: Add `page.on('pageerror')` and `page.on('console')` to a debug test. If the page is blank, check for auth redirects in the call log (`navigated to "https://auth..."` in Playwright output).

---

## 1c. `page.route` Glob vs Query Parameters

### Problem: Mock route doesn't match requests with query params

`page.route('**/api/v1/agents', ...)` does **NOT** match `/api/v1/agents?active_only=true`.

**Symptom**: Catch-all route returns `{}` (empty object) → `response.filter is not a function` → React error boundary → blank page.

**Fix**: Register both with-query and without-query variants:
```typescript
// ❌ Only matches bare path
await page.route('**/api/v1/agents', handler)

// ✅ Also matches with query params
await page.route('**/api/v1/agents?*', handler)  // with query
await page.route('**/api/v1/agents', handler)     // without query
```

**Key rule**: Always check if your API client adds query params (e.g., `axios.get(url, { params })`) and register both route variants.

---

## 1d. `page.route` Ordering — Specific Before Generic

### Problem: Nested RESTful routes shadow each other

`/api/incidents/:id` (GET detail) and `/api/incidents/:id/resolve` (POST action) share the same base pattern. Registering in the wrong order makes the more specific route unreachable:

```typescript
// ❌ Wrong order — /resolve matches /api/incidents/* first, returns detail JSON for POST
await page.route('**/api/incidents/*', handler)        // catches everything
await page.route('**/api/incidents/*/resolve', handler) // never fires
```

**Fix**: Register more specific routes FIRST. For the generic catch, use `route.fallback()` when the URL doesn't apply:

```typescript
// ✅ Specific first
await page.route('**/api/incidents/*/resolve', (route) =>
  route.fulfill({ json: { id: 'inc-1', status: 'resolved' } })
)
await page.route('**/api/incidents/*', (route) => {
  // Defensive: if a /resolve URL somehow reaches here, let it fall through
  if (route.request().url().includes('/resolve')) return route.fallback()
  return route.fulfill({ json: mockIncidentDetail })
})
```

### waitForResponse with method/URL filter

When the same URL pattern is hit with different methods (GET detail + POST resolve), use a callback filter instead of glob:

```typescript
// ❌ Ambiguous — matches both GET and POST
await page.waitForResponse('**/api/incidents/*')

// ✅ Filter by method
await page.waitForResponse((resp) =>
  resp.url().includes('/api/incidents/') && resp.request().method() === 'GET'
)
```

---

## 1e. Layout Page Title Strict Mode Violation

### Problem: Page title text appears in both Layout header and page content

Common SPA pattern: Layout component renders the page title in its header (h2), and the page component also shows the same title as a heading (h3). Playwright strict mode fails:

```
strict mode violation: getByText('Incident Timeline') resolved to 2 elements:
  1) <h2 class="...">Incident Timeline</h2>  (Layout)
  2) <h3 class="...">Incident Timeline</h3>  (Page content)
```

**Fix options**:

```typescript
// Option 1: .first() if any visible element proves the assertion
await expect(page.getByText('Incident Timeline').first()).toBeVisible()

// Option 2: getByRole with level for specificity
await expect(
  page.getByRole('heading', { name: 'Incident Timeline', level: 3 })
).toBeVisible()

// Option 3: scope to the content area
await expect(page.locator('main').getByText('Incident Timeline')).toBeVisible()
```

---

## 2. Selector Pitfalls

### Substring matching (default!)
```typescript
// ❌ text=P1 matches "P1" AND "P100"
await page.locator('text=P1').click();

// ✅ Exact match
await page.getByText('P1', { exact: true }).click();
```

### `/` prefix = regex
```typescript
// ❌ Interpreted as regex
await page.locator('text=/api/v1/chat').click();

// ✅ Use container selector
await page.locator('code:has-text("chat/completions")').click();
```

### Stateful button (onBlur race)
```typescript
// ❌ Re-locating by text causes focus shift → onBlur resets state
await page.click('button:has-text("Delete")');
await page.click('button:has-text("Confirm?")');

// ✅ Structural locator (same DOM position)
const btn = row.locator('button');
await btn.click();  // Delete → Confirm?
await btn.click();  // Confirm? → executes
```

### Selector Priority
1. `getByText(x, { exact: true })` — unique visible text
2. CSS scoping — `.font-medium:has-text("x")`
3. Structural — `page.locator('.divide-y > div').nth(0).locator('button')`
4. `.first()` — last resort

---

## 3. API-Based E2E (Devcontainer-Friendly)

When browser tests aren't feasible, use API client pattern:

| Aspect | Browser | API |
|--------|---------|-----|
| System deps | 12+ GUI libs | None |
| Speed | 2-5s/test | 100-500ms/test |
| Stability | Brittle selectors | Stable contracts |

```typescript
export class APIClient {
  static async createProject(data: CreateProjectRequest) {
    const response = await fetch(`${BASE_URL}/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!response.ok) throw new Error(await response.text());
    return response.json();
  }
}
```

**Tips**:
- Read Pydantic schemas for ALL required fields (don't trust endpoint docs)
- Test business logic prerequisites (e.g., activate phase before creating tasks)
- Trace router prefixes from source code

---

## 4. Live E2E: Mock Auth Token + Real Backend Auth Cascade

### Problem: Mock token triggers signOut cascade

When live E2E tests inject a mock auth token into localStorage but let API calls hit the real backend, **any authenticated endpoint returns 401** → axios response interceptor calls `signOut()` → ProtectedRoute sees `accessToken = null` → redirects to Landing.

**Symptom**: Page shows Landing page or "Sign in to continue" instead of the expected protected page. Confusing because auth injection appears to work (user profile shows in sidebar on first render, then vanishes).

**Root cause chain**:
```
Mock token in localStorage
  → App mounts, reads token, sets accessToken in store ✓
  → App fetches /api/v1/settings (auth-guarded endpoint)
  → Real backend rejects mock token → 401
  → Axios interceptor: if (401) { signOut() }
  → signOut() clears accessToken from store
  → ProtectedRoute: if (!accessToken) redirect to "/"
```

**Fix**: Mock ALL globally-fetched authenticated endpoints, not just `auth/me`:
```typescript
// ❌ Only mocking auth/me — other auth-guarded endpoints still hit real backend
await page.route('**/api/v1/auth/me', handler)

// ✅ Mock every endpoint the app calls on mount that requires auth
await page.route('**/api/v1/auth/me', handler)
await page.route('**/api/v1/settings', handler)        // auth guard: admin_settings
await page.route('**/api/v1/dashboard/**', handler)     // may have auth
await page.route('**/api/v1/projects', handler)         // GET list on dashboard
```

**How to find which endpoints need mocking**: 
1. Check which API calls fire on page mount (React useEffect, useQuery)
2. For each: `curl -s http://localhost:8000/api/v1/<endpoint>` — if 401, must mock
3. Check for `Depends(get_current_user)` or `Depends(require_permission(...))` in FastAPI router

**Key insight**: `page.route()` only intercepts browser requests. `page.request.get()` (Playwright API client) bypasses route interception — don't use it for auth-guarded endpoints in live tests.

**Live E2E helper pattern** (proven working):
```typescript
export async function setupLiveAuth(page: Page) {
  await injectAuth(page)  // localStorage tokens
  await page.route('**/api/v1/auth/me', mockHandler)
  await page.route('**/api/v1/settings', mockHandler)
  await page.route('**/api/v1/dashboard/**', mockHandler)
  await page.route('**/api/v1/projects', mockHandler)
  // Budget, agents, workers — no auth guard → hit real backend ✓
}
```

---

## Pre-Flight Checklist
- [ ] Could text appear as substring of another element? → `exact: true`
- [ ] Does text start with `/`? → use `getByText()` or `code:has-text()`
- [ ] Does button change text on click? → structural locator
- [ ] Is text conditionally rendered? → verify in source
- [ ] `fc-list` empty? → install fonts before testing
- [ ] Live E2E: does the app fetch auth-guarded APIs on mount? → mock those too
