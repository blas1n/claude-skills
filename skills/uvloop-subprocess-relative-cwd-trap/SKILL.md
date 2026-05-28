---
name: uvloop-subprocess-relative-cwd-trap
description: uvloop's subprocess transport raises FileNotFoundError when cwd is a relative path that stock asyncio accepts. tmp_path-based unit tests hide it because pytest fixtures are always absolute.
---

# uvloop subprocess relative-cwd trap

## Problem

`asyncio.create_subprocess_exec(..., cwd=some_path)` behaves differently under uvloop vs stock asyncio when `cwd` is a relative path:

- **Stock asyncio (default test runner, dev hosts)**: resolves the relative path against the current working directory and runs the subprocess normally.
- **uvloop (FastAPI prod default, `uvicorn --loop uvloop`)**: the subprocess transport raises a bare `FileNotFoundError` on the *cwd*, even when the directory plainly exists (`ls`, `Path.exists()`, `mkdir` all agree).

Symptom in production: a subprocess call (e.g. `git init`) fails silently — the exception is swallowed by an outer soft-fail, leaving an empty directory and a `verified=False` run with no visible cause. Unit tests are all green because pytest's `tmp_path` fixture is always absolute, so the relative-vs-absolute distinction never appears.

The real foot-gun is `pydantic-settings` defaults shaped like `var/products` or `data/runs` (relative to the process cwd) — these look fine in dev where the host's cwd happens to be the repo root, but uvloop in a container rejects them.

## Solution

**Force absolute resolution at the path-builder layer**, not at the subprocess call site. Resolving at the builder means every downstream subprocess inherits the fix:

```python
def product_workspace_path(product_id: uuid.UUID) -> Path:
    root = Path(get_settings().product_workspace_root)
    if not root.is_absolute():
        root = Path.cwd() / root
    return root / str(product_id)
```

Then add a regression test that explicitly uses a **relative** settings value, so the bug can't sneak back in under tmp_path:

```python
async def test_paths_are_absolute_even_when_settings_use_relative_root(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(get_settings(), "product_workspace_root", "var/products", raising=False)
    p = product_workspace_path(uuid.uuid4())
    assert p.is_absolute(), f"path must be absolute: {p}"
```

Do **not** try to fix this by passing `cwd=str(path.resolve())` only at the subprocess call — every new caller has to remember it. Fix it once at the builder.

## Key Insights

- **uvloop's subprocess transport is not a drop-in for asyncio's** — it's stricter about cwd. Anywhere your code does `create_subprocess_exec(..., cwd=...)` with a path that *could* be relative, assume uvloop will reject it in prod.
- **`tmp_path` is a stealth absolute-path generator.** Any test that takes a settings root from a fixture inherits absoluteness for free, which masks bugs where production settings supply relative paths. To catch this class of bug, write at least one test that `monkeypatch.chdir(tmp_path)` *and* sets the settings root to a relative string.
- **Soft-fail wrappers hide environment-specific subprocess errors.** When `init_X` swallows exceptions to avoid blocking startup, an environment-specific `FileNotFoundError` becomes an empty directory with no log trail. If you have soft-fail around shellouts, at minimum log the exception with `exc_info=True`.

## Red Flags

- Pydantic settings field whose default is a relative path like `"var/foo"`, `"data/bar"`.
- `asyncio.create_subprocess_exec(..., cwd=settings.something_root)` where `something_root` comes from settings.
- Prod uses `uvicorn --loop uvloop` (the FastAPI default) but tests use the default asyncio runner.
- "Works on my machine / works in tests, empty result in prod" for any feature that shells out.
- Soft-fail blocks like `try: await init_x() except: pass` around subprocess code — the bug will be invisible until you read raw container logs.

## When this fired

BSVibe W2 dogfood (2026-05-27): `init_product_workspace` shelled out to `git init` with `cwd=product_workspace_path(...)`. Settings carried `product_workspace_root="var/products"`. Stock asyncio test suite (2605 tests) green; prod uvloop run created the directory but then `git init` raised `FileNotFoundError` on its own cwd. Soft-fail in the product create flow swallowed the exception → product appeared in DB with an empty workspace → Brief showed "Didn't finish" with no diagnostic.
