---
name: bsvibe-auth-centralization
description: Centralizing auth through auth.bsvibe.dev — products need only BSVIBE_AUTH_URL, not Supabase credentials. JWKS proxy + refresh/logout API on Vercel.
trigger: when adding authentication to a BSVibe product or debugging auth flow across BSVibe ecosystem
---

# BSVibe Auth Centralization Pattern

## Architecture

```
Product Frontend → auth.bsvibe.dev/login (redirect) → Supabase GoTrue
                                                     ↓
Product Frontend ← callback#access_token=xxx ← auth.bsvibe.dev

Product Backend: BsvibeAuthProvider(auth_url="https://auth.bsvibe.dev")
  └→ Fetches JWKS from auth.bsvibe.dev/.well-known/jwks.json (Vercel rewrite → Supabase)
  └→ Refresh via auth.bsvibe.dev/api/refresh (Vercel serverless → Supabase GoTrue)
  └→ Logout via auth.bsvibe.dev/api/logout (Vercel serverless → Supabase Admin API)
```

## Product Setup (minimal)

### Backend
```python
from bsvibe_auth import BsvibeAuthProvider
from bsvibe_auth.fastapi import create_auth_dependency

provider = BsvibeAuthProvider(auth_url=settings.bsvibe_auth_url)
get_current_user = create_auth_dependency(provider)
```

### Config
```python
class Settings(BaseSettings):
    bsvibe_auth_url: str = "https://auth.bsvibe.dev"
```

### Frontend

Use the **exact** pattern below — the auth service has a redirect_uri
allowlist, so random paths silently fall through to `bsvibe.dev/account`.
Every BSVibe sibling frontend (BSage, BSNexus, etc.) uses the same URL
shape.

```typescript
const AUTH_URL = import.meta.env.VITE_AUTH_URL || "https://auth.bsvibe.dev";

// 1. Login redirect — MUST be `${origin}/#/auth/callback` (hash route).
function login() {
  const redirect = encodeURIComponent(`${window.location.origin}/#/auth/callback`);
  window.location.href = `${AUTH_URL}/login?redirect_uri=${redirect}`;
}

// 2. Callback — auth service appends a SECOND hash fragment:
//    "#/auth/callback#access_token=...&refresh_token=...&expires_in=..."
//    URLSearchParams(hash.slice(1)) does NOT work — find the `access_token=`
//    index and slice from there.
export function consumeAuthCallback(): boolean {
  const raw = window.location.hash || "";
  const tokenPart = raw.includes("access_token=")
    ? raw.slice(raw.indexOf("access_token="))
    : "";
  if (!tokenPart) return false;
  const params = new URLSearchParams(tokenPart);
  const accessToken = params.get("access_token");
  const refreshToken = params.get("refresh_token") ?? "";
  const expiresIn = Number(params.get("expires_in") ?? "3600");
  if (!accessToken) return false;
  localStorage.setItem("access_token", accessToken);
  localStorage.setItem("refresh_token", refreshToken);
  localStorage.setItem("expires_at", String(Date.now() + expiresIn * 1000));
  return true;
}

// 3. Consume on app boot BEFORE getAccessToken() runs, then clean URL.
useEffect(() => {
  if (
    window.location.hash.startsWith("#/auth/callback") &&
    consumeAuthCallback()
  ) {
    const dest = window.location.pathname === "/" ? "/dashboard" : window.location.pathname;
    window.history.replaceState(null, "", dest);
  }
  // ... then load user from token
}, []);
```

Works for both HashRouter apps (BSage) and BrowserRouter apps (BSNexus) —
BrowserRouter ignores the hash, so the `#/auth/callback` never becomes a
real route; the effect just runs once and cleans the URL.

### Symptoms when you get it wrong
- Using `${origin}/dashboard` (or any path not on the allowlist):
  auth service redirects to `https://bsvibe.dev/account` after login.
  User never returns to the app.
- Parsing with `URLSearchParams(hash.slice(1))` instead of slicing from
  `access_token=`: first hash fragment is `#/auth/callback`, so
  `get('access_token')` returns null and login appears to succeed but
  no token lands.

### Do not build dev-bypass token flows
Test accounts live on auth.bsvibe.dev. Don't add
`VITE_DEV_BYPASS_TOKEN` / synthetic-user shims to sidestep login in
dev — every environment goes through the real flow.

## What Products Do NOT Need
- SUPABASE_URL
- SUPABASE_JWT_SECRET
- SUPABASE_ANON_KEY
- SUPABASE_SERVICE_ROLE_KEY (unless using Supabase Admin API for non-auth purposes)
- @supabase/supabase-js

## auth.bsvibe.dev Infrastructure (Vercel)
- `/login`, `/logout` — SPA pages (React)
- `/.well-known/jwks.json` — Vercel rewrite to Supabase JWKS (public keys)
- `/api/refresh` — Vercel serverless, calls Supabase GoTrue (needs SUPABASE_URL + ANON_KEY)
- `/api/logout` — Vercel serverless, calls Supabase Admin API (needs SERVICE_ROLE_KEY)

## Key Decisions
1. JWKS via rewrite (not serverless) — no env vars needed, cached by CDN
2. Supabase credentials only in auth.bsvibe.dev Vercel env vars — not in any product
3. anon key is public (Supabase design) but still centralized to avoid duplication
4. service_role_key is sensitive — only in Vercel env vars, never in product code
