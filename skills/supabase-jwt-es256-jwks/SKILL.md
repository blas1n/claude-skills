---
name: supabase-jwt-es256-jwks
description: Supabase JWT가 HS256이 아닌 ES256(ECDSA)을 사용할 때 — jwt_secret으로 검증 실패하며, JWKS endpoint에서 공개키를 가져와야 한다
version: 1.0.0
---

# Supabase JWT ES256 JWKS Auto-Detection

## Problem

Supabase 프로젝트의 JWT 서명 알고리즘이 **ES256 (ECDSA P-256)**인 경우, `jwt_secret` (HS256용 HMAC shared secret)으로 검증하면 실패한다.

- 증상: `Invalid token: The specified alg value is not allowed` 에러
- 근본 원인: Supabase 문서는 HS256을 기본으로 안내하지만, 일부 프로젝트는 ES256을 사용. JWT header의 `alg` 필드가 `ES256`, `kid` 필드가 존재하면 ECDSA 서명
- 흔한 오해: Supabase Dashboard의 "JWT Secret"을 넣으면 모든 경우에 동작할 것이라고 가정

## Detection

JWT header를 디코딩하면 알고리즘을 확인할 수 있다:

```bash
echo "eyJhbGciOiJFUzI1NiIsImtpZCI6Ii..." | base64 -d
# {"alg":"ES256","kid":"49b9c4f9-...","typ":"JWT"}
```

- `alg: HS256` → `jwt_secret` (HMAC) 사용
- `alg: ES256` + `kid` 존재 → JWKS endpoint에서 공개키 필요

## Solution

Supabase의 JWKS endpoint에서 공개키를 가져와 `PyJWK`로 변환한 뒤 검증에 사용:

```python
import httpx
from jwt import PyJWK

def build_auth_provider(supabase_url: str, jwt_secret: str):
    """HS256/ES256 자동 감지 auth provider 생성."""
    if supabase_url:
        try:
            jwks_url = f"{supabase_url}/auth/v1/.well-known/jwks.json"
            resp = httpx.get(jwks_url, timeout=5.0)
            resp.raise_for_status()
            keys = resp.json().get("keys", [])
            if keys:
                jwk_obj = PyJWK(keys[0])
                alg = keys[0].get("alg", "ES256")
                return SupabaseAuthProvider(
                    jwt_secret=jwk_obj.key,  # ECPublicKey 객체
                    algorithms=[alg],
                )
        except Exception:
            pass  # Fall through to HS256

    # Fallback: HS256 with shared secret
    return SupabaseAuthProvider(jwt_secret=jwt_secret)
```

### 핵심 포인트

- `PyJWK(jwk_dict).key`는 `cryptography.hazmat.bindings._rust.openssl.ec.ECPublicKey` 객체를 반환
- `pyjwt`의 `jwt.decode()`는 이 key 객체를 직접 받을 수 있음 (문자열이 아님)
- JWKS URL은 `{supabase_url}/auth/v1/.well-known/jwks.json` — 표준 OpenID Connect Discovery 경로
- JWKS fetch는 앱 시작 시 1회만 하면 됨 (키 로테이션 빈도가 낮음)

### 환경 설정 주의사항

- `supabase_url`이 pydantic-settings의 `.env` 파일에서 로드되려면, `.env` 파일이 **CWD 기준** 경로에 있어야 함
- devcontainer에서 uvicorn이 `/workspace/backend`에서 실행되면 `/workspace/.env`를 못 읽을 수 있음
- 확실한 방법: 환경변수로 직접 전달하거나, `.env`를 프로젝트 루트와 backend 디렉토리 모두에 배치

## Key Insights

- Supabase JWT 알고리즘은 프로젝트마다 다를 수 있다 — **런타임에 JWKS로 감지**하는 것이 가장 안전
- HS256 secret과 ES256 public key는 완전히 다른 타입 — 잘못된 키를 넣으면 "alg not allowed" 에러
- `bsvibe-auth`의 `SupabaseAuthProvider`는 `algorithms` 파라미터를 지원하므로 `["ES256"]` 전달 가능

## Red Flags

- "The specified alg value is not allowed" 에러 → JWT header의 `alg` 확인
- `jwt_secret` 설정했는데 검증 실패 → ES256 프로젝트일 가능성
- JWKS fetch가 빈 응답 → `supabase_url`이 비어있거나 잘못된 URL
- `.env`에 값을 넣었는데 코드에서 빈 문자열 → CWD와 env_file 경로 불일치
