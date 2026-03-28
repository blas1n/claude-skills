# Coding Best Practices

You are a skilled software engineer. Follow these principles for all coding tasks.

## Core Principles

1. **Read before writing** — Understand existing code, conventions, and patterns before making changes.
2. **Type safety** — Use type hints (Python) or TypeScript types. No `any` unless unavoidable.
3. **Small, focused changes** — Each change should do one thing well. Avoid scope creep.
4. **Test coverage** — Write tests for new logic. Maintain or improve existing coverage.
5. **Error handling** — Handle errors at system boundaries. Trust internal code paths.

## Python Standards

- Python 3.11+ with type hints on all public functions
- `async`/`await` for all I/O operations
- `structlog` for logging, `pydantic-settings` for configuration
- `dataclass` for internal data structures, `pydantic.BaseModel` for API boundaries
- `uv` for package management, `ruff` for linting and formatting

## TypeScript Standards

- Strict mode enabled, no implicit `any`
- Prefer `const` over `let`, avoid `var`
- Use named exports, barrel files only at package boundaries
- Error handling with typed error classes

## Refactoring Guidelines

- Extract only when duplication is real (rule of three)
- Rename for clarity before restructuring
- Keep backward compatibility unless explicitly breaking
- Run tests after every refactoring step

## Bugfix Process

1. Reproduce the bug with a failing test
2. Identify root cause (not just symptoms)
3. Fix minimally — don't refactor unrelated code
4. Verify the fix passes the test
5. Check for similar bugs in adjacent code
