---
name: jwt-401-cascading-logout
description: API interceptor 401 handler deletes tokens and redirects to login — if backend JWT verification fails (JWKS unavailable), user gets logged out on every page load
trigger: when user reports "logs in but immediately returns to login page" or "dashboard flashes then redirects to login"
---

# JWT 401 Cascading Logout

## Problem

User logs in successfully → dashboard appears briefly → redirected back to login.
Happens every time, making the app unusable.

## Root Cause Chain

```
1. Frontend stores JWT in localStorage ✓
2. Dashboard mounts → API calls with Bearer token
3. Backend verifies JWT → JWKS fetch fails (network, wrong URL, proxy not deployed)
4. Backend returns 401 for ALL authenticated endpoints
5. Frontend API interceptor catches 401 → clears localStorage → redirects to /login
6. Login → dashboard → 401 → logout → infinite loop
```

## Detection

```bash
# Test from inside the backend container
curl -s -w "\nHTTP %{http_code}" http://localhost:8000/api/status \
  -H "Authorization: Bearer <any-token>"
# If 401 with JWKS error message → this is the issue

# Check JWKS endpoint reachability from backend
curl -s https://auth.example.com/.well-known/jwks.json | head -1
# If HTML instead of JSON → JWKS proxy not working
```

## Solutions

### 1. Fix the JWKS source (root cause)
Ensure the backend can reach the JWKS endpoint. Verify with curl from inside the container.

### 2. Don't clear tokens on every 401 (defense in depth)
```typescript
// BAD — clears tokens on any 401 including JWKS failures
api.interceptors.response.use(res => res, error => {
  if (error.response?.status === 401) {
    localStorage.clear();  // DANGEROUS
    window.location.href = "/login";
  }
});

// BETTER — only clear on explicit auth rejection, not server errors
api.interceptors.response.use(res => res, error => {
  if (error.response?.status === 401) {
    const detail = error.response?.data?.detail || "";
    // Only logout if the TOKEN itself is invalid, not if JWKS fetch failed
    if (detail.includes("expired") || detail.includes("invalid")) {
      localStorage.clear();
      window.location.href = "/login";
    }
    // JWKS errors: show error toast, don't logout
  }
});
```

### 3. Separate "not authenticated" from "auth infrastructure down"
Backend should return different status codes:
- 401: token is invalid/expired (client should re-authenticate)
- 503: auth infrastructure unavailable (client should retry, not logout)

## Key Insight

The 401 interceptor pattern assumes "401 = user's token is bad". But when JWT verification infrastructure fails (JWKS unreachable), the 401 means "server can't verify ANY token" — logging out makes it worse. The interceptor should distinguish between token-level failures and infrastructure-level failures.
