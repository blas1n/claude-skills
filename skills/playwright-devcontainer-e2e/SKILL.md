---
name: playwright-devcontainer-e2e
description: "Playwright E2E Testing in Devcontainer: Browser vs API Tradeoffs when GUI libraries unavailable"
version: 1.0.0
---

# Playwright E2E Testing in Devcontainer: Browser vs API Tradeoffs

**Problem**: Setting up Playwright E2E tests in a devcontainer environment without X11/GUI libraries. Browser tests fail with missing system dependencies. Attempting to install dependencies requires sudo password (unavailable in automated environments).

**Context**: BSNexus devcontainer (Linux Alpine/Ubuntu without GUI) — tried to run Playwright chromium tests. Expected browser-based E2E to work out-of-the-box. Discovered system GUI library dependencies couldn't be installed, forcing pivot to API-based testing.

---

## Challenge: Environment Constraints vs Testing Strategy

### Symptom: Browser Dependency Failures

```bash
> pnpm test:e2e
Error: browserType.launch:
╔══════════════════════════════════════════════════════╗
║ Host system is missing dependencies to run browsers. ║
║ Please install them with:                            ║
║   sudo pnpm exec playwright install-deps             ║
╚══════════════════════════════════════════════════════╝
```

**Root cause**: Devcontainer is a minimal Linux environment without:
- libglib2.0 (Chromium runtime)
- libnss3 (SSL/crypto)
- libx11-6 (X11 windowing)
- libxdamage1, libxfixes3, libxrandr2 (X11 extensions)
- libasound2t64 (audio)

Attempting `playwright install-deps` triggers:
```
sudo: a terminal is required to read the password
```

**Why this matters**:
- Can't use `apt-get install` without root
- Interactive sudo prompts don't work in scripted/automated contexts
- Devcontainer doesn't pre-install browser dependencies for space/efficiency reasons

---

## Solution: API-Based E2E Testing (Preferred)

### Why API-Based Is Better for Devcontainers

| Aspect | Browser Tests | API Tests |
|--------|---------------|-----------|
| **System deps** | 12+ GUI libraries required | None (just Node.js) |
| **Setup time** | 30-60sec (browser download+install) | Instant |
| **Execution speed** | 2-5sec per test | 100-500ms per test |
| **CI/CD friendly** | Requires GUI library layers | Works in any container |
| **Test scope** | UI + API logic | API logic + business rules |
| **Maintainability** | Brittle (selectors change) | Stable (contracts don't) |

### Implementation Pattern

Create `APIClient` helper class instead of page objects:

```typescript
// frontend/e2e/helpers/api-client.ts
export class APIClient {
  static async createProject(data: CreateProjectRequest) {
    const response = await fetch(`${BASE_URL}/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Failed: ${response.statusText} - ${error}`);
    }
    return response.json();
  }

  static async transitionTask(taskId: string, data: TransitionTaskRequest) {
    // Similar pattern for all API endpoints
  }
}
```

Then write tests using API client:

```typescript
// frontend/e2e/specs/api-integration.spec.ts
test('should complete full project workflow', async () => {
  const project = await APIClient.createProject({...});
  const phase = await APIClient.createPhase(project.id, {...});
  await APIClient.activatePhase(project.id, phase.id);  // Business logic prerequisite!

  const task = await APIClient.createTask({...});
  expect(task.status).toBe('ready');  // Only true if phase is active

  // Transition through full lifecycle
  await APIClient.transitionTask(task.id, {new_status: 'queued', actor: 'test'});
  // ... verify each state
});
```

---

## Discovery: Hidden API Schema Requirements

### Pattern: Required Fields in POST Bodies

Problem: Tests failed with `422 Unprocessable Entity` because schemas require fields that aren't documented in endpoint descriptions.

**Phase creation failing:**
```json
{
  "detail": [
    {"type": "missing", "loc": ["body", "description"], "msg": "Field required"}
  ]
}
```

**Task creation failing:**
```json
{
  "detail": [
    {"type": "missing", "loc": ["body", "description"], "msg": "Field required"},
    {"type": "missing", "loc": ["body", "priority"], "msg": "Field required"}
  ]
}
```

**Solution**: Trace Pydantic schemas in backend code to find required fields.

```python
# backend/src/schemas.py
class PhaseCreate(BaseModel):
    name: str
    description: str  # Required, not optional
    order: int

class TaskCreate(BaseModel):
    project_id: UUID
    phase_id: UUID
    title: str
    description: str  # Required
    priority: str     # Required
    worker_prompt: str
    qa_prompt: str
```

**Pattern to avoid cascade failures**:
1. Read Pydantic schema first (not endpoint docs)
2. Provide ALL required fields in test data
3. Expect `422` if fields are missing — check `response.text()` for details

---

## Discovery: Business Logic Dependencies

### Problem: Task Initial Status Depends on Phase State

Tests expected tasks to start in `"ready"` status, but they initialized as `"waiting"`:

```typescript
const phase = await APIClient.createPhase(project.id, {
  name: 'Phase 1',
  description: 'Phase 1',  // Required!
  order: 1,
});
// ❌ WRONG — phase is "pending", tasks will be "waiting"

const task = await APIClient.createTask({...});
expect(task.status).toBe('ready');  // Fails — actually "waiting"!
```

**Root cause**: Task status initialization logic checks phase status:

```python
# backend/src/core/orchestrator.py
if phase.status == PhaseStatus.active:
    initial_status = TaskStatus.ready
else:
    initial_status = TaskStatus.waiting  # Because phase is "pending"
```

**Solution**: Activate phases before creating tasks:

```typescript
const phase = await APIClient.createPhase(project.id, {...});
await APIClient.activatePhase(project.id, phase.id);  // NEW!

const task = await APIClient.createTask({...});
expect(task.status).toBe('ready');  // Now passes ✓
```

**Lesson**: Business logic prerequisites must be discovered by reading source code or trial-and-error. Document these in test setup.

---

## Pattern: Endpoint Path Discovery

### Problem: Guessing Router Prefixes

Initially tried:
```typescript
// ❌ WRONG — returns 404
fetch(`/api/v1/projects/phases/${phaseId}`, {method: 'PATCH'})

// ✅ CORRECT — matches router definition
fetch(`/api/v1/projects/phases/${phaseId}`, {method: 'PATCH'})
```

Both look the same, but the issue was the full router prefix. Discovered by reading source:

```python
# backend/src/api/projects.py
router = APIRouter(prefix="/api/v1/projects", tags=["projects"])
# ...
@router.patch("/phases/{phase_id}", response_model=PhaseResponse)
```

This means the full path is `/api/v1/projects` (prefix) + `/phases/{phase_id}` (route) = `/api/v1/projects/phases/{phase_id}`.

**Discovery approach**:
1. Check `router.include_router(projects.router)` in main.py for prefix
2. Grep `@router.patch` / `@router.post` in source file
3. Concatenate: `{BASE_URL}{router_prefix}{route_path}`

---

## Checklist: API-Based E2E in Devcontainer

Before writing tests:

- [ ] No browser dependencies needed — use API client only
- [ ] Read Pydantic schemas for ALL required fields (don't trust docs)
- [ ] Test each business logic prerequisite (e.g., activate phase before creating tasks)
- [ ] Trace router prefixes from source code, don't guess
- [ ] Add detailed error messages: `response.text()` for debugging 422/400 errors
- [ ] Use `APIClient` helper pattern to avoid HTTP boilerplate
- [ ] Catch early: run single test first, fix schema issues before bulk tests

---

## Example: Complete API-Based E2E Test

```typescript
test('should transition task through complete lifecycle', async () => {
  // 1. Create project
  const project = await APIClient.createProject({
    name: `Test Project ${Date.now()}`,
    description: 'Test',
    repo_path: '/test/repo',
  });

  // 2. Create and activate phase (PREREQUISITE!)
  const phase = await APIClient.createPhase(project.id, {
    name: 'Phase 1',
    description: 'Test phase',  // Required field
    order: 1,
  });
  await APIClient.activatePhase(project.id, phase.id);

  // 3. Create task (will start as 'ready' because phase is active)
  const task = await APIClient.createTask({
    project_id: project.id,
    phase_id: phase.id,
    title: `Task ${Date.now()}`,
    description: 'Test task',    // Required field
    priority: 'medium',           // Required field
    worker_prompt: 'Work',
    qa_prompt: 'QA',
  });
  expect(task.status).toBe('ready');
  expect(task.version).toBe(1);

  // 4. Transition through states
  let t = task;
  for (const status of ['queued', 'in_progress', 'review', 'done']) {
    t = await APIClient.transitionTask(t.id, {
      new_status: status,
      actor: 'test',
      expected_version: t.version,  // Enforce optimistic locking
    });
    expect(t.status).toBe(status);
    expect(t.version).toBe(t.version + 1);
  }

  // 5. Verify final state
  const final = await APIClient.getTask(task.id);
  expect(final.status).toBe('done');
  expect(final.version).toBe(5);  // 1 initial + 4 transitions
});
```

---

## When to Choose Browser Tests Instead

API-based E2E is not a complete replacement. Use browser tests when:

- **Visual regression**: Screenshot comparisons needed
- **UI interactions**: Complex form flows, drag-drop, real-time updates
- **Accessibility**: WCAG compliance testing
- **Cross-browser**: Need to test Safari, Firefox, Edge behavior

**For these cases**, either:
1. Run browser tests on CI/CD system WITH pre-installed browser dependencies
2. Use Docker container specifically for browser testing
3. Use cloud-based browser service (BrowserStack, LambdaTest)

---

## Summary Table

| Scenario | Solution | Why |
|----------|----------|-----|
| **Devcontainer, no GUI deps** | Use API-based E2E | Avoids sudo/dependencies, CI/CD friendly |
| **Local dev with GUI** | Use browser tests | Can test UI interactions, visual testing |
| **CI/CD pipeline** | Use API tests | Lightweight, deterministic, fast |
| **Critical user flows** | Use BOTH | API for logic, browser for UX |

