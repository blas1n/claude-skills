---
name: orchestrate-worktree-prompts
description: Reusable claude -p prompt templates for common orchestration tasks
---

# Prompt Templates

Reusable `claude -p` prompt templates for `.agent/PROMPT.md`.
Select and customize based on the task type.

## Base Prompt (Always Include)

```
You are a developer working on this project.

Read .agent/tasks.json and select the highest-priority task where passes is false.
Implement it according to the description and acceptanceCriteria.

After implementation:
1. Verify: uv run ruff check . && uv run ruff format --check . && uv run pytest
2. If verification passes: git commit with descriptive message
3. Update .agent/tasks.json: set passes to true for the completed task
4. Append findings/learnings to .agent/progress.txt

For REVIEW tasks:
- Run git diff main and review ALL changes
- Check: security, code quality, type hints, test quality, architecture rules, bugs, style
- If issues found: fix them, then add a NEW review task to tasks.json (passes:false)
- Only mark passes:true when ZERO issues remain (including minor ones)

IMPORTANT: Only work on ONE task per invocation. Do not skip ahead.
```

## Task-Specific Addons

Append these to the base prompt depending on the work type.

### Structlog Migration

```
Migration rules:
- import logging → import structlog; logger = structlog.get_logger(__name__)
- logging.info/warning/error → logger.info/warning/error with structured kwargs
- logging.getLogger → structlog.get_logger
- Convert format strings: logger.info("msg %s", val) → logger.info("event_name", key=val)
- Add structlog to pyproject.toml dependencies
- Create structlog configuration (JSON renderer for prod, console for dev)
- Do NOT name the config file logging.py (shadows stdlib)
```

### Test Coverage

```
Testing rules:
- Target: 80%+ coverage
- Mock ALL external APIs (LLM, HTTP, database, filesystem)
- Use pytest-asyncio for async tests
- Follow existing test patterns in tests/ directory
- Include edge cases: empty input, None values, error paths
- Use tmp_path fixture for filesystem operations
- Add conftest.py with shared fixtures if missing
- Run: uv run pytest --cov --cov-fail-under=80
```

### Security Hardening

```
Security review checklist:
- No hardcoded secrets or default passwords (check .env.example too)
- Auth bypass: verify all endpoints require authentication
- Input validation: all user inputs validated via Pydantic
- CORS: no wildcard origins with credentials
- Rate limiting: verify per-tenant/user limits exist
- Error messages: no credential/token leakage
- Temp files: try/finally cleanup
- subprocess: no shell=True
```

### Dependency Update

```
Dependency update rules:
- Update versions in pyproject.toml
- Run uv lock to regenerate lockfile
- Run full test suite to verify compatibility
- Check for breaking changes in changelogs
- Update any deprecated API usage
```

### Pre-commit Setup

```
Pre-commit setup:
- Use ruff for both linting and formatting (NOT black)
- Standard config from ~/Works/_infra/templates/pre-commit-config.yaml
- Install: pip install pre-commit && pre-commit install
- Verify: pre-commit run --all-files
```

### Code Review (for REVIEW tasks)

```
Review with zero tolerance for issues:
1. Security: input validation, auth bypass, hardcoded values, credential leaks
2. Code quality: missing type hints, error handling, edge cases, dead code
3. Test quality: vacuous assertions, missing edge cases, test isolation
4. Architecture: structlog (not logging), pydantic-settings (not os.getenv), async I/O
5. Style: unused imports, naming consistency, docstring format
6. Bugs: logic errors, race conditions, resource leaks, shadowed variables

Fix ALL issues found, then re-verify.
If you fixed anything, add a new REVIEW task to tasks.json for another pass.
Only mark passes:true when you find ZERO issues.
```
