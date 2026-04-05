---
name: auth-jwt-patterns
description: "Auth/JWT patterns — ES256 JWKS auto-detection, 401 cascading logout prevention, OAuth callback token relay for SPAs"
version: 1.0.0
triggers:
  - pattern: "JWT verification fails with alg mismatch, user gets logged out on every page load, or OAuth callback loses tokens"
---

# Auth & JWT Patterns

## 1. Supabase JWT ES256 JWKS Auto-Detection

Supabase JWT 알고리즘이 **ES256 (ECDSA)**인 경우, `jwt_secret` (HS256)으로 검증하면 실패.

**Detection**: JWT header의 `alg` 확인:
```bash
echo "eyJhbGciOiJFUzI1Ni..." | base64 -d
# {"alg":"ES256","kid":"49b9c4f9-..."}
```

**Solution**: JWKS endpoint에서 공개키 자동 감지:
```python
import httpx
from jwt import PyJWK

def build_auth_provider(supabase_url: str, jwt_secret: str):
    if supabase_url:
        try:
            resp = httpx.get(f"{supabase_url}/auth/v1/.well-known/jwks.json", timeout=5.0)
            keys = resp.json().get("keys", [])
            if keys:
                return SupabaseAuthProvider(
                    jwt_secret=PyJWK(keys[0]).key,  # ECPublicKey 객체
                    algorithms=[keys[0].get("alg", "ES256")],
                )
        except Exception:
            pass
    return SupabaseAuthProvider(jwt_secret=jwt_secret)  # HS256 fallback
```

- JWKS URL: `{supabase_url}/auth/v1/.well-known/jwks.json`
- `PyJWK(jwk_dict).key` → `ECPublicKey` 객체 (문자열 아님)
- 앱 시작 시 1회 fetch

---

## 2. 401 Cascading Logout Prevention

**Problem**: 로그인 성공 → 대시보드 → API 401 → 토큰 삭제 → 로그인 → 무한 루프

**Root cause**: JWKS fetch 실패 시 backend가 모든 토큰에 401 반환. Frontend interceptor가 401=토큰 무효로 처리.

```typescript
// ❌ 모든 401에서 로그아웃
api.interceptors.response.use(res => res, error => {
  if (error.response?.status === 401) {
    localStorage.clear();
    window.location.href = "/login";  // JWKS 장애 시 무한 루프
  }
});

// ✅ 토큰 자체가 무효할 때만 로그아웃
api.interceptors.response.use(res => res, error => {
  if (error.response?.status === 401) {
    const detail = error.response?.data?.detail || "";
    if (detail.includes("expired") || detail.includes("invalid")) {
      localStorage.clear();
      window.location.href = "/login";
    }
    // JWKS/인프라 에러: 에러 토스트, 로그아웃 안함
  }
});
```

**Best practice**: Backend에서 토큰 무효 → 401, 인프라 장애 → 503 분리.

---

## 3. OAuth Callback Token Relay for SPAs

**Problem**: 서버 리다이렉트로 hash fragment 토큰 전달 시 프록시가 fragment 유실.

**Solution**: HTML relay page 반환:
```python
@public.get("/auth/callback")
async def auth_callback(request: Request) -> HTMLResponse:
    params_json = json.dumps(dict(request.query_params))
    html = f"""<!DOCTYPE html>
<html><body><script>
(function() {{
  var p = {params_json};
  var h = window.location.hash.substring(1);
  if (h) new URLSearchParams(h).forEach(function(v,k) {{ p[k] = v; }});
  if (p.access_token) localStorage.setItem('app_access_token', p.access_token);
  if (p.refresh_token) localStorage.setItem('app_refresh_token', p.refresh_token);
  window.location.replace('/');
}})();
</script></body></html>"""
    return HTMLResponse(content=html)
```

**Key points**:
- 인증 서버가 query param vs hash fragment 중 어느 쪽으로 토큰을 보내는지 사전 확인 불가 → 양쪽 모두 파싱
- E2E 테스트: `page.addInitScript(() => localStorage.setItem("token", "test"))`
- HTTP 환경: `crypto.randomUUID()` 불가 → `Math.random().toString(36)` 대안

---

## 4. React StrictMode + SSO Redirect Infinite Loop

Silent SSO check via `window.location.href` redirect breaks in React StrictMode.

**Symptom**: Landing page endlessly reloads (white flash loop).

**Root cause**:
1. `checkSession()` → no local session → redirect to `auth.bsvibe.dev/api/silent-check`
2. Auth server returns with `?sso_error=1` (no active session)
3. `checkSession()` detects `sso_error` → removes from URL via `history.replaceState` → returns `null`
4. **StrictMode calls `initialize()` a second time**
5. Second call: no local session, no `sso_error` in URL (already removed) → redirects again → **infinite loop**

**Fix**: Use `sessionStorage` flag to survive URL rewrites within the same browser session:
```typescript
// session.ts
const SSO_CHECKED_KEY = 'bsvibe_sso_checked';
export function markSSOChecked(): void { sessionStorage.setItem(SSO_CHECKED_KEY, '1'); }
export function wasSSOChecked(): boolean { return sessionStorage.getItem(SSO_CHECKED_KEY) === '1'; }
export function clearSSOChecked(): void { sessionStorage.removeItem(SSO_CHECKED_KEY); }

// client.ts checkSession()
if (searchParams.get('sso_error')) {
  markSSOChecked();  // ← persist before URL cleanup
  // ... remove sso_error, return null
}
if (wasSSOChecked()) return null;  // ← guard before redirect

// On successful login:
clearSSOChecked();  // ← reset for next session
```

**Key insight**: Any SSO flow that modifies URL state + relies on `useEffect` is vulnerable to StrictMode double-invocation. The URL mutation (replaceState) is NOT rolled back by StrictMode cleanup, but the effect IS re-run.

---

## Red Flags
- "alg value not allowed" → JWT header의 `alg` 확인 (ES256 vs HS256)
- 로그인 성공 후 즉시 로그인 화면 → 401 interceptor + JWKS 장애
- callback 후 세션 없음 → hash fragment 유실, relay page 필요
- 랜딩 페이지 무한 리로딩 → StrictMode + SSO redirect loop (sessionStorage 플래그 필요)
