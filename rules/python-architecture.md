---
description: Common Python architecture rules for all projects
---

# Python Architecture Rules

## CRITICAL: Core Architectural Decisions

These decisions are final. Do NOT deviate without explicit approval.

### 1. Python-Only, uv for Package Management

**All code MUST be Python 3.11+.**

**NEVER use requirements.txt. Use pyproject.toml + uv only:**

```toml
# pyproject.toml
[project]
dependencies = [
    "pydantic-settings>=2.0.0",
    "structlog>=23.0.0",
]
```

Why: Single source of truth, uv is faster and more reliable.

### 2. Type Hints Required

**ALL public functions MUST have type hints.**

```python
# Correct
async def process_item(item_id: str) -> ItemResult:
    pass

# Wrong
async def process_item(item_id):  # NO!
    pass
```

### 3. pydantic-settings for Configuration

**ALWAYS use pydantic-settings for environment variable management.**

```python
# Correct
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = ""
    api_key: str = ""
    debug: bool = False

    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()  # Auto-validates at startup

# Wrong
import os
api_key = os.getenv('API_KEY')  # No validation, no type safety
```

### 4. structlog for Logging

**ALWAYS use structlog for structured JSON logging.**

```python
# Correct
import structlog
logger = structlog.get_logger(__name__)

logger.info("task_completed",
            task_name="process-data",
            duration_s=1.2,
            items_processed=42)

# Wrong
import logging
logging.info("Task completed")  # Unstructured, hard to parse

# Wrong
print("Task completed")  # Never use print for logging
```

### 5. Async Throughout

**ALL I/O operations MUST be async.**

```python
# Correct
async def fetch_data(source: str) -> dict:
    result = await client.get(source)
    await save_result(result)
    return result

# Wrong
def fetch_data(source):  # Blocks event loop!
    pass
```

### 6. Dataclasses for Internal Data

**Use dataclasses for structured internal data, NOT dict.**

```python
# Correct
from dataclasses import dataclass

@dataclass
class TaskItem:
    name: str
    status: str
    priority: int
    metadata: dict | None = None

# Wrong
task = {"name": "...", "status": "..."}  # No type safety
```

### 7. PYTHONPATH Configuration

**NEVER use sys.path.insert() for imports.**

```python
# Wrong
import sys
sys.path.insert(0, "/workspace")

# Correct — PYTHONPATH set in devcontainer / editable install
from myapp.core.config import settings
```

### 8. Output/Tmp Paths via Environment

**ALWAYS configure output and temporary paths via environment variables or settings.**

```python
# Correct — configurable
output_path = settings.output_dir / "results" / f"{slug}.json"

# Wrong — hardcoded path
Path("/Users/me/data") / filename
```

### 9. Temporary Files in TMP_DIR

**ALL temporary files go in a configured temp directory.**

```python
# Correct
tmp_dir = settings.tmp_dir / task_name
tmp_dir.mkdir(parents=True, exist_ok=True)

# Wrong
Path("/tmp") / task_name  # Ignores configured tmp path
```

## Verification Checklist

Before implementing ANY module:
- [ ] Python 3.11+ with type hints on all public functions
- [ ] pyproject.toml + uv (no requirements.txt)
- [ ] pydantic-settings for config (no raw os.getenv)
- [ ] structlog for logging (not print or logging.info)
- [ ] async for all I/O operations
- [ ] Dataclasses for internal data structures
- [ ] No sys.path.insert()
- [ ] Output/tmp paths from settings

## Git Commit Rules

**NEVER include Co-Authored-By in commit messages.**

Commit message format:
```
type(scope): short description

- bullet points for details
- no Co-Authored-By line
```

Example:
```bash
git commit -m "feat(core): add task processor with async pipeline

- Process items from queue asynchronously
- Store results via configured output path
- Add structured logging for each step"
```
