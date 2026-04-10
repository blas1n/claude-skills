---
name: mock-fixtures-hide-wiring-bugs
description: "FastAPI dependency_overrides + pre-seeded test fixtures silently hide whether production glue (auth wrapper, middleware upsert, lifespan-time hooks) is wired into the request flow at all. 100% green unit tests can ship dead code that 500s on the first real request. Defense: real-backend integration tests with no overrides + no pre-seeding."
version: 1.0.0
---

# Mock Fixtures Hide Wiring Bugs

## When to Use

Any FastAPI / Flask / Django service where:
- Unit tests use ``app.dependency_overrides[...] = mock_xxx`` to bypass auth, DB sessions, or external clients, **and**
- Test fixtures pre-seed required rows (a default Tenant, a User, an org, a Project) before each test runs, **and**
- "Glue" code lives inside the layer that the override replaces — middleware upserts, dependency wrappers, post-auth hooks.

If all three are true, the test suite has a **structural blindspot**: no test exercises whether the glue is actually wired into the request chain.

## The Failure Mode

Real example, from a session that took hours to diagnose:

1. Backend defined ``ensure_personal_tenant(db, tenant_id, user)`` to upsert a personal Tenant row on first authenticated request. Without it, every FK insert (agents, projects, goals) crashes with ``ForeignKeyViolationError`` because ``tenants.id`` does not exist yet.
2. ``test_tenant_context.py`` had two unit tests calling the function directly:
   ```python
   async def test_ensure_personal_tenant_inserts_row(db_session): ...
   async def test_ensure_personal_tenant_is_idempotent(db_session): ...
   ```
   Both green. The function was demonstrably correct.
3. Every API test (``test_agent_api.py``, ``test_agent_templates_api.py``, ``test_budget_api.py``, ...) had this fixture:
   ```python
   @pytest.fixture(autouse=True)
   async def _seed_default_tenant(db_session):
       db_session.add(Tenant(id=DEFAULT_TENANT_ID, ...))
       await db_session.commit()
       yield
   ```
   So a Tenant row already existed before any handler ran.
4. The shared ``client`` fixture overrode ``get_current_user``:
   ```python
   test_app.dependency_overrides[get_current_user] = lambda: mock_user
   ```
   So the wrapping function that *should* have called ``ensure_personal_tenant`` was never executed by the test suite.
5. Result: **989 backend tests green, 89 mock-mode e2e green**, but ``ensure_personal_tenant`` was **dead code** — no production code path called it. A brand-new bsvibe.dev account hitting "Apply Template" 500'd on the first request: ``insert or update on table 'agents' violates foreign key constraint``.

The bug is the *absence* of an integration step. Unit tests cover behavior; nothing covers wiring.

## Why Coverage Tools Cannot Save You

Line coverage shows ``ensure_personal_tenant`` at 100% — the unit tests hit every line. Branch coverage agrees. ``mypy`` is happy. ``ruff`` is happy. The function looks fine in isolation; the fact that *no production code calls it from a request handler chain* is invisible to every static and per-line tool.

## The Defense: Real-Backend Integration Tests

Spin up a real PostgreSQL container, run a real ``uvicorn`` subprocess against it, and hit the running service over real HTTP from inside pytest. **No** ``dependency_overrides``, **no** pre-seeded ``Tenant``, **no** ``mock_user`` — let the bypass token (or a real signed JWT) walk the same TenantMiddleware → get_current_user → handler chain that production traffic does.

Properties that matter:
- **Empty DB at boot.** Migrations run on a fresh container, then the very first request must succeed without anyone manually inserting a row first.
- **No FastAPI dependency overrides.** If you replace ``get_current_user`` with a lambda, you have just removed the bug from view.
- **Real network roundtrip.** ASGI ``TestClient`` is fine for most tests but it shares the process. Subprocess + httpx catches lifespan / ASGI-middleware issues that ``TestClient`` quietly skips.

```python
# backend/tests/test_integration_fresh_db.py — sketch
import subprocess, uuid, httpx, pytest

@pytest.fixture(scope="module")
def live_backend():
    pg = f"bsx-int-pg-{uuid.uuid4().hex[:6]}"
    subprocess.run(["docker", "run", "-d", "--rm", "--name", pg, ..., "postgres:16-alpine"], check=True)
    try:
        wait_for_pg(pg)
        env = {**os.environ, "DATABASE_URL": database_url, "E2E_TEST_TOKEN": TOKEN, ...}
        subprocess.run(["uv", "run", "alembic", "upgrade", "head"], env=env, check=True)
        backend = subprocess.Popen(["uv", "run", "uvicorn", "backend.src.main:app", "--port", str(port)], env=env)
        wait_for_http(f"http://127.0.0.1:{port}/api/v1/...")
        yield f"http://127.0.0.1:{port}"
    finally:
        backend.terminate(); subprocess.run(["docker", "rm", "-f", pg])


def test_first_authenticated_request_upserts_tenant(live_backend):
    # No fixture seeded the Tenant row. If ensure_personal_tenant is not
    # wired into the request chain, this 500s with FK violation.
    with httpx.Client(base_url=live_backend, headers={"Authorization": f"Bearer {TOKEN}"}) as c:
        r = c.post("/api/v1/agents", json={"name": "first", "role": "dev", "executor_type": "claude_api"})
    assert r.status_code == 201
    assert r.json()["tenant_id"] == EXPECTED_TENANT
```

That single test would have caught the bug at PR time. Every additional test (apply template, create project, ...) gets the same protection for free.

## Bypass Token Pattern (env-gated)

Real bsvibe.dev / Auth0 / Supabase JWT verification needs a valid signing key. To avoid faking JWKS for tests, ship an env-gated bypass:

```python
# backend/src/core/auth.py
async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> BSVibeUser:
    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if settings.e2e_test_token and token == settings.e2e_test_token:
        user = _build_e2e_test_user()  # synthetic admin
    else:
        user = await auth_provider.verify_token(token)  # real path
    await ensure_personal_tenant(db, _tenant_id_from_user(user), user)
    return user
```

Make the bypass token a JWT-formatted opaque string so the **frontend** can ``decodeJwt`` it for user display, while the **backend** treats it as exact-match-only. Both ends hardcode the same constant; signature is junk:

```ts
// frontend/e2e/helpers/live-token.ts
const HEADER  = base64UrlEncode({ alg: "HS256", typ: "JWT" })
const PAYLOAD = base64UrlEncode({ sub: "e2e-user", email: "e2e@x.test", exp: 9999999999, app_metadata: { tenant_id, role: "admin" } })
export const E2E_TEST_TOKEN = `${HEADER}.${PAYLOAD}.e2e-fake-signature`
```

Production never sets ``E2E_TEST_TOKEN``, so the bypass is dead code there. Tests set it via the subprocess env. Browser e2e seeds it via ``page.addInitScript`` into ``localStorage`` before navigation.

## Checklist

Before declaring "tests cover this":
- [ ] Is the production code path inside a layer that any test fixture replaces (``dependency_overrides``, monkeypatch, mock fixture)?
- [ ] Does any test exercise the ``request → middleware → wrapped dep → handler`` chain end-to-end against a real DB?
- [ ] Could the mocked-out wrapper be empty (or wired to ``pass``) and the suite still pass?
- [ ] If a brand-new user makes their first authenticated request, what fails first? Is *that* path tested?
- [ ] Are there pre-seed fixtures (``_seed_default_tenant``, ``_seed_user``, ``_seed_project``) that mask "the FIRST X must work" cases?

If two or more answers are wrong, you have this blindspot. Add a ~10-line subprocess integration test before adding any more unit tests.

## Why Not TestClient Instead of Subprocess?

``fastapi.testclient.TestClient`` (or httpx ``ASGITransport``) runs in the same process. That is fine for most things, but:
- Lifespan-time hooks (``on_startup``, ``Depends`` evaluated during ``app.state``) can be skipped or duplicated.
- Async dispatcher loops you start in ``lifespan`` keep running and can deadlock the test pool.
- Module-level ``importlib.reload`` to swap settings is fragile — caches inside other modules survive the reload.

A throwaway uvicorn subprocess sidesteps every one of these. The cost is ~5 seconds of cold-start per module, which buys you a test that exactly matches production startup.

## Why This Skill Exists

I shipped a feature branch with 989 green backend tests, 89 green mock-e2e tests, 80%+ coverage. Every "Apply Template" press in production 500'd because ``ensure_personal_tenant`` was never wired into any handler chain. The fix was three lines (wrap ``get_current_user``); the wasted hours were spent assuming the test suite proved the function was reachable. It did not, and no test in that style ever could.

The cure was a single ``test_integration_fresh_db.py`` that runs four ~3-second scenarios against a real uvicorn subprocess on an empty PG container, with no overrides and no pre-seeding. Adding it took 30 minutes. It will save the same hours every time someone forgets to wire glue going forward.
