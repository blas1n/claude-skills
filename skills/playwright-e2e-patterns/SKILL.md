---
name: playwright-e2e-patterns
description: "Playwright E2E patterns — devcontainer setup (fonts, system libs), selector pitfalls, API-based testing"
version: 1.0.0
triggers:
  - pattern: "writing Playwright E2E tests, elements report hidden in Docker, or strict mode selector violations"
---

# Playwright E2E Patterns

## 1. Devcontainer Environment Setup

### Missing Fonts = All Text "Hidden"
Minimal Docker images have zero fonts. Chromium can't render text → zero dimensions → `toBeVisible()` fails on ALL text.

**Diagnosis**: `fc-list` returns empty.

**Fix (Dockerfile)**:
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core fontconfig && rm -rf /var/lib/apt/lists/*
```

**Fix (no root)**: Install via micromamba:
```bash
export MAMBA_ROOT_PREFIX=$HOME/.mamba
micromamba create -n pw-deps -c conda-forge -y fonts-conda-forge font-ttf-dejavu-sans-mono fontconfig
mkdir -p ~/.fonts && ln -sf $MAMBA_ROOT_PREFIX/envs/pw-deps/fonts/* ~/.fonts/
```

Set in `playwright.config.ts`:
```typescript
use: {
  launchOptions: {
    env: {
      ...process.env,
      FONTCONFIG_PATH: resolve(homedir(), '.config/fontconfig'),
      FONTCONFIG_FILE: resolve(homedir(), '.config/fontconfig/fonts.conf'),
    },
  },
},
```

### Missing System Libraries
Chromium needs `libnss3`, `libgbm`, etc. For libs not in conda-forge, create minimal stub `.so` files.

---

## 2. Selector Pitfalls

### Substring matching (default!)
```typescript
// ❌ text=P1 matches "P1" AND "P100"
await page.locator('text=P1').click();

// ✅ Exact match
await page.getByText('P1', { exact: true }).click();
```

### `/` prefix = regex
```typescript
// ❌ Interpreted as regex
await page.locator('text=/api/v1/chat').click();

// ✅ Use container selector
await page.locator('code:has-text("chat/completions")').click();
```

### Stateful button (onBlur race)
```typescript
// ❌ Re-locating by text causes focus shift → onBlur resets state
await page.click('button:has-text("Delete")');
await page.click('button:has-text("Confirm?")');

// ✅ Structural locator (same DOM position)
const btn = row.locator('button');
await btn.click();  // Delete → Confirm?
await btn.click();  // Confirm? → executes
```

### Selector Priority
1. `getByText(x, { exact: true })` — unique visible text
2. CSS scoping — `.font-medium:has-text("x")`
3. Structural — `page.locator('.divide-y > div').nth(0).locator('button')`
4. `.first()` — last resort

---

## 3. API-Based E2E (Devcontainer-Friendly)

When browser tests aren't feasible, use API client pattern:

| Aspect | Browser | API |
|--------|---------|-----|
| System deps | 12+ GUI libs | None |
| Speed | 2-5s/test | 100-500ms/test |
| Stability | Brittle selectors | Stable contracts |

```typescript
export class APIClient {
  static async createProject(data: CreateProjectRequest) {
    const response = await fetch(`${BASE_URL}/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!response.ok) throw new Error(await response.text());
    return response.json();
  }
}
```

**Tips**:
- Read Pydantic schemas for ALL required fields (don't trust endpoint docs)
- Test business logic prerequisites (e.g., activate phase before creating tasks)
- Trace router prefixes from source code

---

## Pre-Flight Checklist
- [ ] Could text appear as substring of another element? → `exact: true`
- [ ] Does text start with `/`? → use `getByText()` or `code:has-text()`
- [ ] Does button change text on click? → structural locator
- [ ] Is text conditionally rendered? → verify in source
- [ ] `fc-list` empty? → install fonts before testing
