---
name: code-quality
description: Run after completing code changes to verify quality standards (ruff, mypy, pytest)
---

# Code Quality Skill

Run this skill after completing code changes to verify quality standards.

## Verification Steps

1. **Run Ruff (Linting)**
```bash
uv run ruff check <src_dir>/
```
Must pass with 0 errors.

If errors found, fix with:
```bash
uv run ruff check <src_dir>/ --fix
```

2. **Run MyPy (Type Checking)**
```bash
uv run mypy <src_dir>/
```
Must pass with 0 errors.

3. **Run Tests**
```bash
uv run pytest tests/ -v
```
All tests must pass.

## Common Ruff Fixes

| Rule | Issue | Fix |
|------|-------|-----|
| F401 | Unused import | Remove the import |
| F821 | Undefined name | Add import or fix typo |
| E501 | Line too long | Break line (max 88 chars) |
| I001 | Import order | Let ruff --fix handle it |

## Common MyPy Fixes

| Error | Fix |
|-------|-----|
| `Missing type parameters for generic type` | Use `dict[str, Any]` not `dict` |
| `Function is missing a return type` | Add `-> ReturnType` or `-> None` |
| `Returning Any from function` | Use explicit `str()`, `float()` cast |
| `has no attribute` on union | Use `hasattr()` check or `isinstance()` |

## Forbidden Patterns

- `# type: ignore` — Fix the actual type issue
- `# noqa` — Fix the actual lint issue
- Function-level imports — Move to module top
- Missing type hints — Add complete annotations
- Generic types without parameters — Use `list[str]` not `list`
