---
name: saas-frontend-backend-domain-split
description: SaaS deployment requires separate domains for frontend (CDN) and backend (API) — serving both from one domain causes 404s or requires complex rewrites
version: 1.0.0
task_types: [devops, design]
triggers:
  - pattern: "deploying SaaS with frontend and backend on same domain, or getting 404 on product URLs"
---

# SaaS Frontend/Backend Domain Split

## Problem

When deploying a SaaS product, a common mistake is pointing the product domain (e.g., `gateway.bsvibe.dev`) directly at the backend API server. Users visit the URL and get a 404 or API error instead of the frontend SPA.

## Wrong Approach

```
gateway.bsvibe.dev → Caddy → localhost:4000 (FastAPI backend)
→ User visits gateway.bsvibe.dev → 404 (no frontend files served)
```

Even if the Dockerfile builds the frontend into the Docker image, you need explicit static file serving configuration. This is fragile and loses CDN benefits.

## Correct Architecture

Split into two domains:

```
gateway.bsvibe.dev     → Vercel/CDN (frontend SPA)
api-gateway.bsvibe.dev → Reverse proxy → backend API
```

### Domain Naming Convention

| Frontend (CDN) | Backend (API) |
|---------------|---------------|
| `gateway.bsvibe.dev` | `api-gateway.bsvibe.dev` |
| `nexus.bsvibe.dev` | `api-nexus.bsvibe.dev` |

- Do NOT use abbreviations (`api-gw` → `api-gateway`)
- Do NOT use subdomain nesting (`gateway.api.bsvibe.dev`) — adds DNS complexity

### DNS Configuration (Cloudflare)

| Type | Name | Target | Proxy |
|------|------|--------|-------|
| CNAME | `gateway` | `cname.vercel-dns.com` | **DNS only** (gray cloud) |
| A | `api-gateway` | server IP | **Proxied** (orange cloud) |

- Vercel domains MUST be DNS only — Vercel handles its own TLS
- API domains use Cloudflare proxy for free TLS + DDoS protection

### Frontend Environment

Set `VITE_API_URL` (or equivalent) in Vercel:
```
VITE_API_URL=https://api-gateway.bsvibe.dev
```

### CORS

Backend `CORS_ALLOWED_ORIGINS` must match the frontend domain:
```
CORS_ALLOWED_ORIGINS=https://gateway.bsvibe.dev
```

## Key Insight

The product domain belongs to the user — it should show the UI. The API is infrastructure — it gets a separate, predictable subdomain. This also enables CDN edge caching for the frontend while keeping the API on your own server.
