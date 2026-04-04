---
name: cloudflare-origin-cert-caddy-setup
description: Cloudflare Origin Certificate + Caddy reverse proxy setup — PEM file naming trap and brew services configuration
version: 1.0.0
task_types: [devops]
triggers:
  - pattern: "setting up Cloudflare origin certificate with Caddy, or getting TLS PEM errors in Caddy"
---

# Cloudflare Origin Certificate + Caddy Setup

## Problem 1: PEM File Name Swap

Cloudflare Origin Certificate 다운로드 시, 사용자가 "Origin Certificate"을 `.pem`으로, "Private Key"를 `.key`로 저장하는데, **실제 내용이 뒤바뀌어 저장되는 경우**가 빈번하다.

### Symptom

```
Error: tls: failed to find certificate PEM data in certificate input,
but did find a private key; PEM inputs may have been switched
```

### Diagnosis

```bash
head -1 origin.pem  # "-----BEGIN PRIVATE KEY-----" → 잘못됨!
head -1 origin.key  # "-----BEGIN CERTIFICATE-----" → 잘못됨!
```

### Fix

```bash
cd ~/certs/bsvibe.dev
mv origin.pem tmp.pem
mv origin.key origin.pem
mv tmp.pem origin.key
# origin.pem = CERTIFICATE, origin.key = PRIVATE KEY
```

## Problem 2: Caddy brew services Config Path

`brew services start caddy`는 `/opt/homebrew/etc/Caddyfile`을 읽는다. `~/Caddyfile`을 수정해도 반영 안 됨.

### Fix

```bash
ln -sf ~/Caddyfile /opt/homebrew/etc/Caddyfile
brew services restart caddy
```

### Reload without restart

```bash
caddy reload --config ~/Caddyfile
```

## Problem 3: Cloudflare SSL Mode

- **Full (Strict)**: Origin Certificate 필수 (Caddy에 설정)
- **Full**: Self-signed OK (`tls internal` in Caddyfile)
- **Flexible**: 백엔드 HTTP OK (보안 취약)

Origin Certificate 사용 시 반드시 **Full (Strict)** 선택.

## Caddyfile Template

```caddyfile
api-gateway.bsvibe.dev {
    tls /path/to/origin.pem /path/to/origin.key
    reverse_proxy localhost:4000
}
```

Wildcard cert (`*.bsvibe.dev`)이면 모든 서브도메인에 같은 인증서 재사용 가능.
