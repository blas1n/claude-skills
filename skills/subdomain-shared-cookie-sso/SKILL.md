# Subdomain Shared Cookie SSO

## When to Apply

- Multiple products on subdomains of the same domain (e.g., `*.bsvibe.dev`)
- Central auth server (e.g., `auth.bsvibe.dev`) handles login/signup
- Products need SSO — login once, authenticated everywhere

## Core Pattern

Set `Domain=.parent.dev` on the httpOnly session cookie from the auth server.
All subdomains automatically share the cookie. No per-product callback pages needed.

```
Set-Cookie: session=xxx; HttpOnly; Secure; SameSite=Lax; Domain=.parent.dev; Path=/
```

### Auth Flow (Final)

```
1. User clicks login on product-a.parent.dev
2. → auth.parent.dev/login (no redirect_uri needed)
3. → OAuth/password auth → auth.parent.dev/callback
4. → Set shared cookie (Domain=.parent.dev) → redirect to default destination
5. User visits product-b.parent.dev → cookie sent automatically → authenticated
```

### What Becomes Unnecessary

- Per-product `/auth/callback` pages
- Per-product token relay (hash fragment passing)
- Per-product localStorage auth state
- Per-product `redirect_uri` parameters
- Multiple entries in OAuth provider's allowed redirect list

## Traps

### 1. `Secure` Flag Blocks HTTP Local Dev

**Symptom**: Login succeeds, POST /api/session returns 200, but cookie is never set. Browser silently rejects `Secure` cookies on `http://`.

**Fix**: Make `Secure` conditional:
```typescript
const SECURE = import.meta.env.DEV ? '' : ' Secure;';
// Set-Cookie: session=xxx; HttpOnly;${SECURE} SameSite=Lax; Domain=...
```

### 2. Auth Server Must Allow Missing redirect_uri

**Symptom**: "Missing redirect_uri parameter" error when login page is opened without `?redirect_uri=...`.

**Fix**: Auth server login/signup pages should default to a sensible destination (e.g., `bsvibe.dev/account`) when redirect_uri is omitted. Only validate redirect_uri when explicitly provided.

```typescript
const effectiveRedirectUri = redirectUri || 'https://bsvibe.dev/account';
const validation = redirectUri ? validateRedirectUri(redirectUri) : { valid: true };

// After auth success:
if (redirectUri) {
  // Legacy: send tokens in hash fragment for unmigrated products
  window.location.href = buildCallbackUrl(redirectUri, { tokens });
} else {
  // Shared cookie already set, just redirect
  window.location.href = effectiveRedirectUri;
}
```

### 3. Backward Compatibility with Unmigrated Products

Products not yet on shared cookie still need hash fragment tokens. Support both:
- `redirect_uri` present → legacy flow (tokens in hash)
- `redirect_uri` absent → cookie-only flow (simple redirect)

### 4. Supabase OAuth `uri_allow_list` Must Include Auth Callback

**Symptom**: Google login redirects to `site_url` instead of auth server's callback.

Supabase `authorize` endpoint's `redirect_to` parameter is checked against `uri_allow_list`. If the auth server's callback URL isn't in the list, Supabase falls back to `site_url`.

**Fix**: `uri_allow_list` should contain ONLY the auth server's callback:
```
https://auth.parent.dev/callback
```
Not individual product callbacks — those are no longer needed with shared cookies.

### 5. Cross-Subdomain Logout

DELETE the cookie with the same `Domain=.parent.dev`:
```
Set-Cookie: session=; HttpOnly; Secure; SameSite=Lax; Domain=.parent.dev; Path=/; Max-Age=0
```
Logging out on any subdomain clears the cookie for all subdomains.

## Cookie Spec (Reference)

| Attribute | Value |
|-----------|-------|
| Name | `bsvibe_session` (or app-specific) |
| Value | Refresh token |
| HttpOnly | `true` |
| Secure | `true` (prod), conditional (dev) |
| SameSite | `Lax` |
| Domain | `.parent.dev` |
| Path | `/` |
| Max-Age | 2,592,000 (30 days) |

## Origin

Discovered during bsvibe-site web app hub transformation (2026-04-09).
Three iterations: client-side localStorage → per-product httpOnly cookie → shared domain cookie.
The shared cookie approach eliminated ~90% of auth-related code from each product.
