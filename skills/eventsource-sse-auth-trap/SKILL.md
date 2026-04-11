---
name: eventsource-sse-auth-trap
description: "Browser EventSource API cannot send Authorization headers. SSE endpoints protected by JWT auth silently 401 in production — passes in tests because mock-mode e2e skips the real endpoint entirely, and dev-mode often runs without auth. Fix: accept ?token= query param as fallback."
version: 1.0.0
---

# EventSource SSE Auth Trap

## When to Use

Any SPA + API architecture where:
- Backend SSE endpoints are guarded by the same JWT auth middleware as REST routes, **and**
- The frontend opens SSE connections via the browser `EventSource` API, **and**
- Tests use mock-mode (intercepting `page.route()`) so the real SSE endpoint is never hit

If all three are true, you have a **silent production auth bug**: the SSE stream 401s on every real connection, but no test catches it because neither the mock e2e nor the unit tests exercise the real SSE + auth flow.

## Why It's Silent

1. **Mock e2e**: `page.route('**/chat/events', ...)` returns a canned `text/event-stream` response. The browser never opens a real `EventSource` to the backend. The endpoint could return 500 for all you know.

2. **Dev devcontainer**: Often the auth check is effectively disabled (the test app overrides `get_current_user` with a mock, or the dev token is already in a cookie from a prior login session, or the endpoint was marked `@public` during prototyping and nobody noticed).

3. **Unit tests**: Test the SSE generator function in isolation — `_chat_event_generator(project_id, redis)` — never going through the ASGI middleware that actually checks auth.

4. **The browser's EventSource API has NO header injection**. You cannot pass `Authorization: Bearer ...`. `fetch()` can do it, `XMLHttpRequest` can do it, but `new EventSource(url)` sends only cookies. If your auth is bearer-token-only (no session cookies on the API domain), the SSE request arrives with **zero credentials**.

## The Fix

Accept the bearer token via query string as a fallback:

```python
# backend/src/core/auth.py
async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> BSVibeUser:
    # Token resolution order:
    #   1. Authorization: Bearer <token> — preferred
    #   2. ?token=<token> — required for SSE (EventSource has no header API)
    raw_token = ""
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        raw_token = auth_header.split(" ", 1)[1].strip()
    elif "token" in request.query_params:
        raw_token = (request.query_params.get("token") or "").strip()

    if not raw_token:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    # ... same verify_token / bypass logic as before ...
```

Frontend:

```typescript
// hooks/useChatEvents.ts
const connect = async () => {
  const token = await getAccessToken()
  const url = token
    ? `/api/v1/projects/${id}/chat/events?token=${encodeURIComponent(token)}`
    : `/api/v1/projects/${id}/chat/events`
  const source = new EventSource(url)
  // ...
}
```

## Why Not Use `fetch()` + `ReadableStream` Instead?

`fetch()` supports custom headers and would avoid the query-string token:

```typescript
const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
const reader = res.body.getReader()
```

This works but loses automatic reconnection (EventSource retries on network errors with exponential backoff out of the box). You'd have to reimplement the retry + last-event-id logic manually. For most projects the `?token=` query param is the pragmatic choice.

## Security Considerations

- The token appears in server access logs and potentially in browser history. This is acceptable for **short-lived JWTs** (sub-1-hour expiry) — the token is already visible in the Authorization header of every REST call in the same log.
- For **long-lived opaque tokens**, prefer a cookie-based session or the `fetch()` + `ReadableStream` approach instead.
- The backend should always prefer the `Authorization` header when both are present — never let the query param override a valid header. This prevents a subtle CSRF vector where a crafted link with `?token=attacker_token` overrides a legitimate session.

## How This Was Found

An isolated e2e orchestrator (throwaway PG + Redis + uvicorn + vite + worker) ran all specs against a fresh stack with auth enforcement. Every SSE endpoint returned 401, killing the chat sidebar and plan-tree live updates. The symptom was "chat message sent but no response ever appears" — the backend processed the message and published the SSE event, but the browser's EventSource was in a retry loop against 401 and never received it. The 90-second safety timeout eventually cleared the typing indicator and surfaced a toast, but by then the user had already refreshed.

Mock-mode e2e (89 tests, all green) could never catch this because `page.route()` intercepted the SSE URL before it reached the server. The bug had been live since the auth middleware was added to the SSE routes and was only discovered when the isolated stack forced a real connection.

## Checklist

Before shipping any new SSE endpoint:
- [ ] Does the endpoint have auth? If yes, does the browser `EventSource` have a way to pass credentials?
- [ ] Is the token passed via query string? If so, is it short-lived?
- [ ] Does the frontend `EventSource` constructor include the `?token=` param?
- [ ] Is there a **real** (non-mocked) e2e test that opens the SSE endpoint and asserts events arrive?
- [ ] Does the auth dependency prefer the header over the query param when both are present?
