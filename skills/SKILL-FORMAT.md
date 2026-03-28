# SKILL.md Format Standard

Every skill directory under `skills/` must contain a `SKILL.md` file with YAML frontmatter defining its manifest. This document specifies the required and optional fields.

## Frontmatter Schema

```yaml
---
name: skill-name                    # Required. Kebab-case identifier, must match directory name.
description: One-line description   # Required. Used for trigger matching and registry display.
version: 1.0.0                     # Required. Semver (MAJOR.MINOR.PATCH).
task_types: [coding, refactor]     # Optional. BSNexus executor matching tags (see Task Types below).
executor: claude_code              # Optional. Target executor (default: claude_code).
required_tools: [Edit, Write]      # Optional. Claude Code tools the skill needs.
allowed-tools: Read Write Edit     # Optional. Space-separated tools (Claude Code native format).
triggers:                          # Optional. Conditions that auto-invoke this skill.
  - pattern: "description of when to trigger"
metadata:                          # Optional. Additional key-value pairs.
  argument-hint: "[args]"
---
```

## Field Details

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Kebab-case identifier matching the directory name. Used as the skill's unique ID. |
| `description` | `str` | One-line description. Claude Code uses this for trigger matching. Be specific. |
| `version` | `str` | Semantic version (`MAJOR.MINOR.PATCH`). Bump MAJOR for breaking changes, MINOR for new features, PATCH for fixes. |

### Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `task_types` | `list[str]` | `[]` | Tags for BSNexus executor matching. See standard types below. |
| `executor` | `str` | `claude_code` | Which executor runs this skill. |
| `required_tools` | `list[str]` | `[]` | Tools the skill needs (array format). |
| `allowed-tools` | `str` | — | Tools the skill needs (space-separated, Claude Code native format). |
| `triggers` | `list[dict]` | `[]` | Auto-trigger conditions with `pattern` descriptions. |
| `metadata` | `dict` | `{}` | Arbitrary key-value pairs (e.g., `argument-hint`). |

### Standard Task Types

Use these values in `task_types` for consistent BSNexus executor matching:

| Type | Description |
|------|-------------|
| `coding` | General code writing and implementation |
| `refactor` | Code restructuring and improvement |
| `bugfix` | Bug diagnosis and fixing |
| `testing` | Test writing and test infrastructure |
| `debugging` | Systematic debugging workflows |
| `devops` | CI/CD, deployment, infrastructure |
| `content_writing` | Blog posts, documentation, copy |
| `analysis` | Data analysis and reporting |
| `design` | Architecture and system design |
| `review` | Code review and quality checks |
| `workflow` | Multi-step process orchestration |

## Examples

### Minimal Valid SKILL.md

```yaml
---
name: my-skill
description: Brief description of what this skill does
version: 1.0.0
---

# My Skill

Skill content here...
```

### Full-Featured SKILL.md

```yaml
---
name: fastapi-guidelines
description: FastAPI backend development guidelines with DDD layering and async patterns.
version: 1.0.0
task_types: [coding, refactor]
executor: claude_code
required_tools: [Read, Edit, Write, Bash]
triggers:
  - pattern: "code imports fastapi or user asks about FastAPI development"
---

# FastAPI Backend Development Guidelines

Skill content here...
```

### Skill with Claude Code Native Fields

```yaml
---
name: mermaid
description: Generate Mermaid diagrams from user requirements.
version: 1.0.0
task_types: [design]
allowed-tools: Read Write Edit
metadata:
  argument-hint: "[diagram description or requirements]"
---

# Mermaid Diagram Generator

Skill content here...
```

## Directory Structure

```
skills/
├── SKILL-FORMAT.md          # This document
├── my-skill/
│   ├── SKILL.md             # Manifest (required)
│   ├── prompt.md            # Extended prompt (optional)
│   └── references/          # Supporting files (optional)
└── _registry.json           # Auto-generated index
```

## Validation Rules

1. Frontmatter must be valid YAML between `---` delimiters
2. `name` must match the directory name
3. `version` must be valid semver
4. `task_types` values should use standard types listed above
5. Either `required_tools` (array) or `allowed-tools` (space-separated) may be used, not both

## Backward Compatibility

Existing skills with only `name` and `description` remain valid but are considered incomplete. The registry generator will index them with default values for missing optional fields.
