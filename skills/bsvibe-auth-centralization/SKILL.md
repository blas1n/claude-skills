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
```typescript
const AUTH_URL = "https://auth.bsvibe.dev";
// Login: redirect to auth.bsvibe.dev/login?redirect_uri=${origin}/auth/callback
// Callback: extract tokens from URL hash fragment (#access_token=xxx)
// Store: localStorage
// No Supabase SDK needed
```

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
