#!/usr/bin/env python3
"""Generate skills/_registry.json from SKILL.md frontmatter.

Walks skills/ directory, parses YAML frontmatter from each skill's SKILL.md
(or prompt.md as fallback), and outputs a flat JSON array to skills/_registry.json.

Usage:
    python3 scripts/generate-registry.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# PyYAML is optional — fall back to a minimal regex-based parser
try:
    import yaml

    def parse_yaml(text: str) -> dict:
        return yaml.safe_load(text) or {}

except ImportError:
    def parse_yaml(text: str) -> dict:
        """Minimal YAML parser for flat key-value frontmatter."""
        result: dict = {}
        for line in text.strip().splitlines():
            match = re.match(r'^(\w[\w-]*)\s*:\s*(.+)$', line)
            if not match:
                continue
            key, value = match.group(1), match.group(2).strip()
            # Parse inline lists: [a, b, c]
            list_match = re.match(r'^\[(.+)]$', value)
            if list_match:
                result[key] = [v.strip().strip('"').strip("'") for v in list_match.group(1).split(',')]
            elif value.lower() in ('true', 'false'):
                result[key] = value.lower() == 'true'
            elif value.startswith('"') and value.endswith('"'):
                result[key] = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                result[key] = value[1:-1]
            else:
                result[key] = value
        return result


FRONTMATTER_RE = re.compile(r'^---\s*\n(.+?)\n---', re.DOTALL)

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
REGISTRY_PATH = SKILLS_DIR / "_registry.json"


def extract_frontmatter(filepath: Path) -> dict | None:
    """Extract YAML frontmatter from a markdown file."""
    try:
        content = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"  WARNING: cannot read {filepath}: {exc}", file=sys.stderr)
        return None

    match = FRONTMATTER_RE.match(content)
    if not match:
        return None

    try:
        return parse_yaml(match.group(1))
    except Exception as exc:
        print(f"  WARNING: invalid YAML in {filepath}: {exc}", file=sys.stderr)
        return None


def build_entry(skill_dir: Path, frontmatter: dict) -> dict:
    """Build a registry entry from parsed frontmatter."""
    rel_path = skill_dir.relative_to(SKILLS_DIR)
    return {
        "name": frontmatter.get("name", skill_dir.name),
        "path": f"skills/{rel_path}",
        "description": frontmatter.get("description", ""),
        "version": frontmatter.get("version", "0.0.0"),
        "task_types": frontmatter.get("task_types", []),
        "executor": frontmatter.get("executor", "claude_code"),
    }


def _is_skill_dir(path: Path) -> bool:
    """Return True if the directory contains a SKILL.md or prompt.md."""
    return any((path / c).exists() for c in ("SKILL.md", "prompt.md"))


def generate_registry() -> list[dict]:
    """Recursively walk skills/ and build registry entries.

    Supports both flat (skills/mermaid/) and nested (skills/coding/general/)
    layouts.  A directory is treated as a skill when it contains SKILL.md or
    prompt.md.  Parent directories (e.g. skills/coding/) that lack these files
    are traversed but not indexed.
    """
    entries: list[dict] = []

    if not SKILLS_DIR.is_dir():
        print(f"ERROR: skills directory not found at {SKILLS_DIR}", file=sys.stderr)
        sys.exit(1)

    for skill_dir in sorted(SKILLS_DIR.rglob("*")):
        if not skill_dir.is_dir():
            continue
        if any(part.startswith(("_", ".")) for part in skill_dir.relative_to(SKILLS_DIR).parts):
            continue
        if not _is_skill_dir(skill_dir):
            continue

        # Try SKILL.md first, then prompt.md
        frontmatter = None
        for candidate in ("SKILL.md", "prompt.md"):
            filepath = skill_dir / candidate
            if filepath.exists():
                frontmatter = extract_frontmatter(filepath)
                if frontmatter is not None:
                    break

        if frontmatter is None:
            rel = skill_dir.relative_to(SKILLS_DIR)
            print(f"  WARNING: no valid frontmatter in {rel}/", file=sys.stderr)
            continue

        # Validate required fields
        missing = [f for f in ("name", "description", "version") if not frontmatter.get(f)]
        if missing:
            rel = skill_dir.relative_to(SKILLS_DIR)
            print(
                f"  WARNING: {rel}/ missing required fields: {', '.join(missing)}",
                file=sys.stderr,
            )

        entries.append(build_entry(skill_dir, frontmatter))

    return entries


def main() -> None:
    print(f"Scanning {SKILLS_DIR} ...")
    entries = generate_registry()

    REGISTRY_PATH.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Generated {REGISTRY_PATH} with {len(entries)} skills.")


if __name__ == "__main__":
    main()
