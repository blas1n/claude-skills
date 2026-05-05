# Skills Index

Auto-generated from `SKILL.md` frontmatter — do not edit by hand.
Total: 81 skills.

## Think & Plan (7)

- **`/autoplan`** — Auto-review pipeline — reads the full CEO, design, and eng review skills from disk
- **`/deep-interview`** — Requirements clarification through Socratic questioning with mathematical ambiguity scoring. Prevents 'that's not what I meant' outcomes.
- **`/mermaid`** — Generate Mermaid diagrams from user requirements. Supports flowcharts, sequence diagrams, class diagrams, ER diagrams, Gantt charts, and 18 more diagram types.
- **`/office-hours`** — YC Office Hours — two modes. Startup mode: six forcing questions that expose
- **`/plan-design-review`** — Designer's eye plan review — interactive, like CEO and Eng review.
- **`/plan-eng-review`** — Eng manager-mode plan review. Lock in the execution plan — architecture,
- **`/writing-plans`** — Use when you have a spec or requirements for a multi-step task, before touching code

## Build & Code (4)

- **`/coding-general`** — Generic coding skill for implementation, refactoring, and bugfix tasks
- **`/fastapi-guidelines`** — FastAPI backend development guidelines. Domain-Driven Design with Router→Service→Repository layering, SQLModel/SQLAlchemy ORM, async patterns, Pydantic validation, error handling, and TestClient testing.
- **`/feature-workflow`** — TDD+E2E 전체 워크플로우. 기능 작업 시작 전 테스트/체크리스트 작성, 구현, 검증, 커밋까지 안내.
- **`/test-driven-development`** — Use when implementing any feature or bugfix, before writing implementation code

## Debug & Investigate (2)

- **`/investigate`** — Systematic debugging with root cause investigation. Four phases: investigate,
- **`/systematic-debugging`** — Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes

## Review & Quality (6)

- **`/ai-slop-cleaner`** — AI-generated code cleanup — deletion-first approach, regression-safe. Removes unnecessary abstractions, verbose comments, and over-engineering.
- **`/cso`** — Chief Security Officer mode. Infrastructure-first security audit: secrets archaeology,
- **`/design-review`** — Designer's eye QA: finds visual inconsistency, spacing issues, hierarchy problems,
- **`/iterative-subagent-review-loop`** — Use when reviewing and hardening a branch before merge. Runs a fix→verify→sub-agent-review loop until zero issues remain. Effective for large branches (10+ files) where single-pass review misses integration bugs.
- **`/review`** — Pre-landing PR review. Analyzes diff against the base branch for SQL safety, LLM trust
- **`/verification-before-completion`** — Use when about to claim work is complete, fixed, or passing, before committing or creating PRs - requires running verification commands and confirming output before making any success claims; evidence before assertions always

## Test (9)

- **`/asyncpg-testing-patterns`** — asyncpg testing — mock at repository level (preferred) or use @asynccontextmanager for pool/transaction mocking
- **`/benchmark`** — Performance regression detection using the browse daemon. Establishes
- **`/mcp-python-sdk-testing`** — Test mcp Python SDK servers without spawning subprocesses — extract registered handlers from server.request_handlers and invoke ListToolsRequest/CallToolRequest objects directly. Result is wrapped in ServerResult.root.
- **`/mock-testing-patterns`** — Mock testing patterns — context setup gotchas, blindspot review for high-coverage code, plugin testing tiers
- **`/playwright-e2e-patterns`** — Playwright E2E patterns — devcontainer setup (fonts, system libs), selector pitfalls, API-based testing
- **`/pytest-asyncmock-unawaited-coroutine`** — Patching async stdlib functions (asyncio.sleep, asyncio.create_subprocess_exec) with AsyncMock causes RuntimeWarning about unawaited coroutines during test teardown
- **`/pytest-coverage-gotchas`** — pytest-cov Coverage Gotchas — diagnosing false coverage failures and async 0% coverage
- **`/qa`** — Systematically QA test a web application and fix bugs found. Runs QA testing,
- **`/test-against-source-contracts`** — Test Against Source Contracts — verify tests match actual API/interface contracts

## Ship & Deploy (3)

- **`/canary`** — Post-deploy canary monitoring. Watches the live app for console errors,
- **`/land-and-deploy`** — Land and deploy workflow. Merges the PR, waits for CI and deploy,
- **`/ship`** — Ship workflow: detect + merge base branch, run tests, review diff, bump VERSION,

## Reflect & Learn (4)

- **`/checkpoint`** — Save and resume working state checkpoints. Captures git state, decisions made,
- **`/learn`** — Manage project learnings. Review, search, prune, and export what gstack
- **`/retro`** — Weekly engineering retrospective. Analyzes commit history, work patterns,
- **`/retrospective`** — AUTO-TRIGGER at task completion when difficulty signals detected (wrong first approach, multiple failures, undocumented behavior). Extract insights from difficult work into reusable skills. Do NOT wait for user — execute immediately.

## Ops & Workflow (4)

- **`/careful`** — Safety guardrails for destructive commands. Warns before rm -rf, DROP TABLE,
- **`/dispatching-parallel-agents`** — Use when facing 2+ independent tasks that can be worked on without shared state or sequential dependencies
- **`/freeze`** — Restrict file edits to a specific directory for the session. Blocks Edit and
- **`/orchestrate-worktree`** — Multi-project worktree orchestration with Ralph Loop — create worktrees, run tasks via claude -p in devcontainers, review until 0 issues, push & PR

## Utilities (3)

- **`/analysis-cost-report`** — BSGateway cost analysis skill for generating usage and cost reports
- **`/bsvibe-auth-centralization`** — Centralizing auth through auth.bsvibe.dev — products need only BSVIBE_AUTH_URL, not Supabase credentials. JWKS proxy + refresh/logout API on Vercel.
- **`/content-blog-post`** — Blog post writing skill for bsvibe.dev/blog style technical content

## Traps & Patterns (retrospective memory) (39)

- **`/absence-measurement-validity-check`** — Before concluding "X doesn't happen" in an integrated system, verify the pipeline that would produce X is actually running. Measuring zero is trivially easy when the producer is off.
- **`/active-passive-dual-dispatch-trap`** — Agent systems with active (planning) and passive (execution) modes can dual-dispatch the same agent, causing it to plan instead of execute
- **`/alembic-fresh-pg-smoke-test`** — SQLite-only unit tests cannot catch PostgreSQL-only migration bugs. Add a fresh-PG smoke test that runs `alembic upgrade head` against an empty container so DROP DEFAULT, enum DDL listener collisions, and dependent-object errors fail at PR time instead of on the next dev's first bootstrap.
- **`/alembic-phantom-revision-from-unpushed-branch`** — Running alembic upgrade from an unpushed local branch against a shared/prod DB stamps an unresolvable revision. Container reboots into restart loop with `Can't locate revision identified by '<id>'`. Diagnose schema impact before resetting alembic_version.
- **`/alembic-postgres-enum-migration`** — Alembic + PostgreSQL Enum Migration — avoid ALTER TYPE ADD VALUE in migrations, use DROP/RECREATE pattern instead
- **`/asyncio-lock-non-reentrant-deadlock`** — Python asyncio.Lock is NOT reentrant — adding locks to fix race conditions can introduce deadlocks when a locked method calls another locked method
- **`/auth-jwt-patterns`** — Auth/JWT patterns — ES256 JWKS auto-detection, 401 cascading logout prevention, OAuth callback token relay for SPAs
- **`/bulk-batch-partial-write-discard`** — Batch processing functions that wrap the WHOLE chunks loop in try/except discard their on-disk partial work in the returned result when any single chunk fails. Symptom — caller logs "0 written" while filesystem actually has N notes. Detection requires real-data e2e + intentional mid-batch failure; single-chunk unit tests miss it.
- **`/devcontainer-infra-traps`** — Devcontainer & Docker traps — dotfiles destroying worktree history, native binding mismatch, compose project name collision
- **`/docker-tailscale-magicdns-no-extrahosts`** — Docker containers on a Tailscale-enabled host already reach tailnet hostnames + 100.x.x.x IPs — do NOT propose docker-compose extra_hosts patches before testing.
- **`/e2e-mock-shape-drift`** — E2E test mock fixtures using wrong API response shape — passes silently because frontend handles malformed data gracefully
- **`/eventsource-sse-auth-trap`** — Browser EventSource API cannot send Authorization headers. SSE endpoints protected by JWT auth silently 401 in production — passes in tests because mock-mode e2e skips the real endpoint entirely, and dev-mode often runs without auth. Fix: accept ?token= query param as fallback.
- **`/fastapi-app-state-fallback-trap`** — FastAPI app.state getattr fallback creates detached default — mutations lost to garbage collection
- **`/internal-module-shadows-pypi-package-in-container`** — A project's src/<name>/ folder named the same as a PyPI package (mcp, jwt, click, …) silently shadows the PyPI install in production container layouts where local dev resolves correctly. Symptom — works on `pytest` and `uvicorn` locally, fails on first import in prod with `cannot import name X from <pkg>`.
- **`/json-column-write-tolerant-read-strict`** — SQLAlchemy JSON / JSONB columns accept any JSON-serializable value on write. The Pydantic response_model on the GET endpoint is strict. A row written as a bare string sits in the DB happily until a fetch hits ResponseValidationError → 500. Producer tests + response-schema tests that don't round-trip via the API miss this.
- **`/large-codebase-deprecation-removal`** — Large Codebase: Graceful Deprecation & Removal Strategy for distributed system patterns
- **`/litellm-tool-call-provider-probe`** — Before writing LiteLLM tool-calling code, run a 10-line probe that asserts tool_calls actually populate for your model+provider combo — some prefixes silently drop the tools parameter.
- **`/llm-context-listing-noise-filter`** — When directory listings feed an LLM prompt with a truncation cap, filter package-manager and build dirs FIRST or the cap silently buries the actual signal under noise. Recurring AI-engineering trap.
- **`/local-llm-agent-safety-nets`** — When building multi-turn agent systems on local/smaller LLMs (Qwen3, gpt-oss, Llama family), never rely on prompt compliance for safety-critical operations. Add backend safety nets for bootstrap/invariants. Triggers — agent system uses local Ollama model, scenario stalls on turn 1, "MAY do X" prompt directives fire only sometimes.
- **`/local-llm-context-vs-generation-budget`** — Local LLMs (ollama, llama.cpp) declare huge context windows (200k+ tokens) but generation time scales with input length. On consumer GPUs, glm-4.7-flash with 16k char input times out at 300s; same model with 5k chars finishes in 50-100s. Cap derived budget for local models — declared context ≠ practical generation budget.
- **`/mock-fixtures-hide-wiring-bugs`** — FastAPI dependency_overrides + pre-seeded test fixtures silently hide whether production glue (auth wrapper, middleware upsert, lifespan-time hooks) is wired into the request flow at all. 100% green unit tests can ship dead code that 500s on the first real request. Defense: real-backend integration tests with no overrides + no pre-seeding.
- **`/multi-agent-chat-architecture`** — Multi-agent chat architecture patterns — synchronous chatbot vs async dispatch, agent routing evolution, SSE real-time delivery
- **`/nextjs-middleware-origin-trap`** — Next.js middleware request.nextUrl.origin returns internal server address (localhost:3000), not the external URL the browser uses — breaks OAuth redirect_uri when behind proxy or port mapping
- **`/ollama-reasoning-model-think-flag`** — Ollama reasoning models (glm-4.7-flash, qwen3-thinking, etc.) emit hundreds of CoT tokens before the actual response unless `think: false` is sent. litellm does NOT forward this kwarg to ollama — visible in extra_kwargs but dropped on the wire. 600s+ timeouts on otherwise-fast prompts.
- **`/playwright-sso-auth-e2e`** — Playwright e2e tests for SPAs with redirect-based SSO (BSVibe Auth, Auth0, Okta etc.) — page.route() cannot intercept window.location.href cross-origin navigation. Use app-side test hooks instead.
- **`/python-asyncio-live-stack-trace`** — Drop-in py-spy alternative for macOS — in-process SIGUSR signal handlers that dump thread tracebacks and asyncio task stacks to a file when the service is hung but you can't restart it.
- **`/python-mutation-traps`** — Python data mutation traps — mutable defaults, dict reference detach, async concurrent modification
- **`/rag-batch-stale-related-context`** — Batched RAG compile pipelines that compute related-notes context ONCE outside the chunk loop and reuse it across chunks silently break the update path. Symptom: classification works, but no existing notes ever get updated — because chunks N+ see context that's irrelevant to their content. Fix: compute related context per chunk, with that chunk's seeds as the query.
- **`/react-19-compiler-lint-migration`** — Fix React 19's strict compiler lint rules in legacy React 18 code — set-state-in-effect, react-hooks/purity, Date.now in render. Idiomatic rewrites without useEffect.
- **`/react-force-graph-d3-force`** — react-force-graph d3Force semantics — modify built-in 'link'/'charge', don't replace. Replacing the link force breaks the canvas because the lib's id-resolution lives inside it.
- **`/saas-frontend-backend-domain-split`** — SaaS deployment requires separate domains for frontend (CDN) and backend (API) — serving both from one domain causes 404s or requires complex rewrites
- **`/sdk-fetch-closure-monkey-patch-trap`** — API SDKs that capture window.fetch at module-init time can't be intercepted by later monkey-patching. Use Playwright page.route() / MSW for tests; use the SDK's own override hook in app code.
- **`/sqlalchemy-model-refactoring-patterns`** — SQLAlchemy Model Refactoring: Field Removal & Migration Patterns for cascading failures
- **`/sqlalchemy-sqlite-pg-compat`** — SQLAlchemy에서 PostgreSQL 전용 기능(partial index, timezone-aware datetime)을 SQLite 테스트 환경과 호환시키는 패턴
- **`/static-ontology-knowledge-graph-trap`** — Hard-coded note_type / category enums in a knowledge system create filing cabinets, not knowledge graphs. The trap: classification looks like success (notes neatly distributed across folders) while the actual graph value (emergent connections, surprising links) stays at zero. Static ontology + LLM classifier = sophisticated tagger, not graph thinking.
- **`/stitch-code-bidirectional-sync`** — Stitch generates screens independently — sidebars/tabs differ per screen. Code must unify, then Stitch must be regenerated to match. One-way sync breaks.
- **`/subdomain-shared-cookie-sso`** — Subdomain Shared Cookie SSO — set Domain=.parent.dev on the auth-server session cookie so every product subdomain automatically authenticates. Avoids per-product callback pages.
- **`/supabase-oauth-redirect-trap`** — Supabase /auth/v1/authorize silently ignores redirect_to values not in uri_allow_list — falls back to site_url with no error. Add the redirect URL to allow list before use.
- **`/uv-git-dependency-cache-trap`** — uv aggressively caches git dependencies — uv sync/pip install won't fetch latest commits without explicit cache clean + lock upgrade
