---
name: oauth-callback-token-relay
description: OAuth callback에서 토큰을 SPA에 안전하게 전달할 때 — redirect/hash fragment 방식이 실패하는 이유와 HTML relay 패턴
version: 1.0.0
---

# OAuth Callback Token Relay for SPAs

## Problem

OAuth/OIDC 인증 후 callback에서 토큰을 SPA에 전달하려 할 때, 서버 리다이렉트(`RedirectResponse`)로 hash fragment를 전달하면 실패한다.

- 증상: 로그인 성공 후 앱이 토큰을 인식하지 못하고 다시 로그인 화면으로 돌아감 (무한 리다이렉트)
- 근본 원인: (1) Hash fragment(`#access_token=...`)는 HTTP 요청에 포함되지 않아 서버가 볼 수 없음. (2) 서버 리다이렉트 시 프록시(vite, nginx)가 Location 헤더의 fragment를 유실할 수 있음. (3) 인증 서버(Supabase 등)가 토큰을 query param이 아닌 hash fragment로 보내는 경우가 많음
- 흔한 오해: `RedirectResponse(url="/#access_token=...")` 하면 브라우저가 fragment를 보존할 것이라고 가정

## Solution

서버 리다이렉트 대신 **HTML relay page**를 반환해서 클라이언트 JS로 토큰을 추출한다:

1. Backend callback 엔드포인트에서 HTMLResponse 반환
2. 인라인 JS가 query params + hash fragment 모두 파싱
3. localStorage에 토큰 저장 후 `window.location.replace('/')` 로 SPA 진입

```python
# FastAPI callback endpoint
@public.get("/auth/callback")
async def auth_callback(request: Request) -> HTMLResponse:
    params = dict(request.query_params)
    params_json = json.dumps(params)
    html = f"""<!DOCTYPE html>
<html><head><title>Authenticating...</title></head>
<body><p>Authenticating...</p><script>
(function() {{
  var p = {params_json};
  // Auth server may send tokens in hash fragment (Supabase convention)
  var h = window.location.hash.substring(1);
  if (h) new URLSearchParams(h).forEach(function(v,k) {{ p[k] = v; }});
  if (p.access_token) localStorage.setItem('app_access_token', p.access_token);
  if (p.refresh_token) localStorage.setItem('app_refresh_token', p.refresh_token);
  window.location.replace('/');
}})();
</script></body></html>"""
    return HTMLResponse(content=html)
```

### 함께 적용해야 할 패턴들

**SPA에서 토큰 기반 auth gate:**
```typescript
// useAuth hook — synchronous localStorage read, no async dependency
export function useAuth() {
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    setToken(localStorage.getItem("app_access_token"));
    setLoading(false);
  }, []);
  // ...
}
```

**E2E 테스트에서 auth bypass:**
```typescript
// Playwright fixture — addInitScript로 토큰 주입
await page.addInitScript(() => {
  localStorage.setItem("app_access_token", "e2e-test-token");
});
```

**HTTP 환경에서 `crypto.randomUUID()` 불가:**
```typescript
// crypto.randomUUID()는 Secure Context (HTTPS) 전용
// HTTP dev 환경에서는 대안 사용
const state = Math.random().toString(36).slice(2) + Date.now().toString(36);
```

## Key Insights

- 인증 서버(Supabase, Auth0 등)가 토큰을 hash fragment로 보내는지 query param으로 보내는지 사전에 확인 불가할 수 있다 — **양쪽 모두 파싱**하는 것이 안전
- Supabase JS client를 "placeholder"로 초기화하면 런타임 크래시 — env가 미설정이면 **Supabase client 자체를 사용하지 않는** 설계가 필요
- React에서 `useEffect`를 조건부 `return` 뒤에 배치하면 hooks 순서 위반으로 **에러 메시지 없이 빈 화면** — 모든 hooks를 조건 분기 전에 호출해야 함

## Red Flags

- OAuth 로그인 성공 후 앱으로 돌아왔는데 세션이 없다 → callback의 토큰 전달 방식 확인
- 서버 로그에 callback 요청이 안 찍힌다 → 토큰이 hash fragment로 오고 있을 가능성
- `createClient(url, key)` 에서 빈 문자열/placeholder 사용 → 초기화 시점 크래시 가능
- 개발 환경(HTTP)에서 `crypto.randomUUID is not a function` → Secure Context API 제한
- 인증 추가 후 E2E 전체 실패 → fixture에서 localStorage 토큰 주입 필요
