#!/usr/bin/env python3
"""One-time migration: add/fix YAML frontmatter in all SKILL.md files."""

from __future__ import annotations
import re
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
FRONTMATTER_RE = re.compile(r'^---\s*\n(.+?)\n---', re.DOTALL)

NO_FRONTMATTER = {
    "alembic-postgres-enum-migration": ("alembic-postgres-enum-migration", "Alembic + PostgreSQL Enum Migration — ALTER TYPE ADD VALUE transaction restriction and autocommit workarounds", ["coding", "debugging"]),
    "asyncpg-repository-testing": ("asyncpg-repository-testing", "asyncpg Repository Testing with AsyncMock — patterns for mocking pool.acquire() in pytest", ["testing"]),
    "fastapi-app-state-fallback-trap": ("fastapi-app-state-fallback-trap", "FastAPI app.state getattr fallback creates detached default — use hasattr guard instead", ["debugging"]),
    "large-codebase-deprecation-removal": ("large-codebase-deprecation-removal", "Large codebase graceful deprecation and removal strategy — phased approach to avoid cascading test failures", ["refactor"]),
    "mock-context-setup-gotchas": ("mock-context-setup-gotchas", "Mock context setup gotchas — forgetting to mock new methods causes silent test failures", ["testing"]),
    "playwright-devcontainer-e2e": ("playwright-devcontainer-e2e", "Playwright E2E testing in devcontainer — browser vs API tradeoffs without X11/GUI", ["testing"]),
    "playwright-selector-pitfalls": ("playwright-selector-pitfalls", "Playwright selector pitfalls and strict mode fixes — substring matching, exact selectors, and click races", ["testing", "debugging"]),
    "plugin-unit-testing-patterns": ("plugin-unit-testing-patterns", "Plugin unit testing patterns — testing entry-point plugins with mock contexts and async execution", ["testing"]),
    "pytest-coverage-gotchas": ("pytest-coverage-gotchas", "pytest-cov coverage gotchas — diagnosing why --cov-fail-under=80 fails when report shows 80%", ["testing", "debugging"]),
    "python-async-concurrent-modification-trap": ("python-async-concurrent-modification-trap", "Python async concurrent modification trap — iterating mutable collections across coroutines causes silent data loss", ["debugging"]),
    "python-dict-reference-detach-trap": ("python-dict-reference-detach-trap", "Python dict reference detach trap — list comprehension filtering creates new list, breaking dict reference", ["debugging"]),
    "python-mutable-defaults-trap": ("python-mutable-defaults-trap", "Python mutable defaults trap — default mutable arguments shared across calls cause state leaks", ["debugging"]),
    "remotion-cli-integration": ("remotion-cli-integration", "Remotion CLI integration from Python subprocess — patterns and pitfalls for video rendering", ["coding"]),
    "sqlalchemy-model-refactoring-patterns": ("sqlalchemy-model-refactoring-patterns", "SQLAlchemy model refactoring — field removal and migration patterns to avoid cascading failures", ["refactor", "coding"]),
    "test-against-source-contracts": ("test-against-source-contracts", "Test against source contracts — validate tests match actual event systems, decorators, and dataclass definitions", ["testing"]),
}

MISSING_VERSION = [
    "asyncio-lock-non-reentrant-deadlock", "asyncpg-transaction-mocking",
    "bisect-boundary-direction-trap", "data-passthrough-enrichment-trap",
    "e2e-mock-shape-drift", "feature-workflow", "gcloud-oauth-ssh-tmux",
    "iterative-subagent-review-loop", "mock-test-blindspot-review",
    "nextjs-middleware-origin-trap", "npx-bin-package-resolution",
    "oauth-callback-token-relay", "orchestrate-worktree",
    "pytest-asyncmock-unawaited-coroutine", "sql-join-or-count-trap",
    "supabase-jwt-es256-jwks", "test-driven-development",
    "uv-git-dependency-cache-trap", "verification-before-completion",
    "writing-plans",
]

def add_frontmatter(skill_dir, name, description, task_types):
    filepath = SKILLS_DIR / skill_dir / "SKILL.md"
    if not filepath.exists():
        print(f"  SKIP: {filepath} does not exist")
        return
    content = filepath.read_text(encoding="utf-8")
    if content.startswith("---"):
        print(f"  SKIP: {skill_dir} already has frontmatter")
        return
    types_str = ", ".join(task_types)
    frontmatter = f"---\nname: {name}\ndescription: {description}\nversion: 1.0.0\ntask_types: [{types_str}]\n---\n\n"
    filepath.write_text(frontmatter + content, encoding="utf-8")
    print(f"  ADDED frontmatter: {skill_dir}")

def add_version(skill_dir):
    for candidate in ("SKILL.md", "prompt.md"):
        filepath = SKILLS_DIR / skill_dir / candidate
        if not filepath.exists():
            continue
        content = filepath.read_text(encoding="utf-8")
        match = FRONTMATTER_RE.match(content)
        if not match:
            continue
        fm_text = match.group(1)
        if re.search(r'^version:', fm_text, re.MULTILINE):
            print(f"  SKIP: {skill_dir}/{candidate} already has version")
            return
        lines = fm_text.split("\n")
        new_lines = []
        inserted = False
        for line in lines:
            new_lines.append(line)
            if line.startswith("description:") and not inserted:
                new_lines.append("version: 1.0.0")
                inserted = True
        if not inserted:
            new_lines.append("version: 1.0.0")
        new_fm = "\n".join(new_lines)
        new_content = content[:match.start(1)] + new_fm + content[match.end(1):]
        filepath.write_text(new_content, encoding="utf-8")
        print(f"  ADDED version: {skill_dir}/{candidate}")
        return
    print(f"  SKIP: {skill_dir} — no file with frontmatter found")

def main():
    print("=== Category 1: Adding full frontmatter ===")
    for skill_dir, (name, desc, types) in sorted(NO_FRONTMATTER.items()):
        add_frontmatter(skill_dir, name, desc, types)
    print("\n=== Category 2: Adding version field ===")
    for skill_dir in sorted(MISSING_VERSION):
        add_version(skill_dir)
    print("\nDone! Run: python3 scripts/generate-registry.py")

if __name__ == "__main__":
    main()
