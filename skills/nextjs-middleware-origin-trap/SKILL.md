---
name: nextjs-middleware-origin-trap
description: Next.js middleware request.nextUrl.origin returns internal server address (localhost:3000), not the external URL the browser uses — breaks OAuth redirect_uri when behind proxy or port mapping
version: 1.0.0
---

# Next.js Middleware Origin Trap

## Problem

`request.nextUrl.origin` in Next.js middleware returns the **internal server address** (e.g., `http://localhost:3000`), not the external URL the user's browser sees (e.g., `http://myserver:13000`).

- 증상: OAuth `redirect_uri`에 `localhost:3000`이 들어가서 인증 서버가 "Redirect origin not allowed" 거부
- 근본 원인: Next.js 서버는 자신이 바인딩된 포트(3000)만 알고, Docker port mapping이나 reverse proxy 뒤의 외부 포트/호스트를 모름
- 흔한 오해: `request.nextUrl.origin`이 브라우저의 `window.location.origin`과 같을 것이라고 가정

## Solution

`Host` 또는 `X-Forwarded-Host` 헤더에서 실제 외부 origin을 추출:

```typescript
function getExternalOrigin(request: NextRequest): string {
  const proto = request.headers.get("x-forwarded-proto") || "http";
  const host =
    request.headers.get("x-forwarded-host") || request.headers.get("host");
  if (host) {
    return `${proto}://${host}`;
  }
  return request.nextUrl.origin; // fallback
}

// Usage in middleware
const origin = getExternalOrigin(request);
const callbackUrl = `${origin}/auth/callback`;
```

### 클라이언트 컴포넌트에서는 다른 패턴

서버사이드(middleware)가 아닌 클라이언트 컴포넌트에서는 `window.location.origin` 사용:

```typescript
"use client";
function handleLogin() {
  const callbackUrl = `${window.location.origin}/auth/callback`;
  window.location.href = `${AUTH_URL}/login?redirect_uri=${encodeURIComponent(callbackUrl)}`;
}
```

## Key Insights

- Next.js middleware는 Edge Runtime에서 실행 — `window` 객체 없음, 서버 컨텍스트
- Docker Compose에서 `ports: "13000:3000"` 매핑 시, 서버 내부는 3000만 인식
- `Host` 헤더는 브라우저가 실제 접근한 `host:port`를 포함 — 가장 신뢰할 수 있는 소스
- Reverse proxy(nginx, Caddy) 뒤에서는 `X-Forwarded-Host`와 `X-Forwarded-Proto`를 확인

## Red Flags

- OAuth redirect 후 "origin not allowed" 에러 → redirect_uri에 들어간 origin 확인
- 개발 환경에서는 되는데 Docker/프록시 환경에서 안 됨 → port mapping 차이
- `request.url`과 `request.nextUrl`이 모두 내부 주소를 반환 → Host 헤더 사용 필요
