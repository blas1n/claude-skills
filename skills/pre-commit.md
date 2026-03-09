---
name: pre-commit
description: Run before creating a git commit to ensure all requirements are met
---

# Pre-commit Skill

Run this skill before creating a git commit to ensure all requirements are met.

## Pre-commit Checklist

### 1. Code Quality (Required)

```bash
# Linting — must pass with 0 errors
uv run ruff check <src_dir>/

# Type checking — must pass with 0 errors
uv run mypy <src_dir>/

# Tests — all must pass
uv run pytest tests/
```

### 2. Code Review

- [ ] All new functions have type hints
- [ ] All new functions have docstrings
- [ ] No hardcoded values (use config/settings)
- [ ] No `# type: ignore` or `# noqa` comments
- [ ] No secrets in code (.env, API keys, credentials)

### 3. Documentation

- [ ] Updated relevant CLAUDE.md if conventions changed
- [ ] Architecture docs updated if design changed

### 4. Security Check

Files that should NEVER be committed:
- `.env` files (use .env.example)
- Credential files (.credentials/, tokens, keys)
- Data directories (data/, outputs/, datasets/)
- Any file containing API keys or credentials

### 5. Git Commit Format

Use conventional commits:

```
<type>(<scope>): <description>

[optional body]
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `refactor`: Code refactoring
- `docs`: Documentation
- `test`: Adding tests
- `chore`: Maintenance

Example:
```
feat(core): add async task processor

- Process items from queue in parallel
- Store results with configurable output path
```

## Auto-fix Commands

```bash
# Fix import order and simple issues
uv run ruff check <src_dir>/ --fix

# Format code
uv run ruff format <src_dir>/
```
