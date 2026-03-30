---
name: cloudflare-pages-functions-limitation
description: Cloudflare Pages static-only deployments silently ignore Functions — use Vercel rewrites or Netlify _redirects for server-side proxying
trigger: when deploying serverless functions on Cloudflare Pages and they return HTML instead of expected response
---

# Cloudflare Pages Functions Limitation

## Problem

Cloudflare Pages Functions (`functions/` directory) may **not execute** even when correctly structured. All paths return the SPA's `index.html` instead.

## Root Cause

- Cloudflare Pages projects initially set up as **static-only** (e.g., via Direct Upload or early Git integration) don't automatically enable Functions when `functions/` is added later
- `_redirects` catch-all (`/* /index.html 200`) takes priority over Functions
- `_routes.json` with `include`/`exclude` may not override static routing

## Detection

```bash
# Every path returns HTML — Functions are NOT running
curl -s https://your-site.com/api/test | head -1
# Output: <!doctype html>
```

## Solutions (ranked)

### 1. Vercel (recommended for BSVibe)
```json
// vercel.json — rewrites are first-class, serverless functions in /api work out of the box
{
  "rewrites": [
    { "source": "/.well-known/jwks.json", "destination": "https://external-api/jwks.json" },
    { "source": "/((?!api/).*)", "destination": "/index.html" }
  ]
}
```

### 2. Netlify
```
# _redirects — 200 status rewrites act as server-side proxy
/.well-known/jwks.json  https://external-api/jwks.json  200
/*  /index.html  200
```

### 3. Cloudflare Pages (if you must)
- Ensure project was created with Git integration (not Direct Upload)
- Functions must be detected at **initial project creation**
- `_routes.json` in build output: `{"version":1,"include":["/api/*"],"exclude":[]}`
- Never use `_redirects` catch-all alongside Functions

## Key Insight

Cloudflare Pages treats "static site" and "full-stack app" as different modes. Adding `functions/` to an existing static project doesn't upgrade it. Vercel and Netlify don't have this distinction — API routes and rewrites work regardless of when they're added.
