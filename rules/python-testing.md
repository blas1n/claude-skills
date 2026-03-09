---
description: Common testing rules and coverage requirements for all Python projects
---

# Testing Rules

## CRITICAL: Tests Are Mandatory

**NEVER commit code without tests.**

**Minimum coverage: 80%**

### Unit Tests Required

Every module MUST have:
- Unit tests for core business logic
- Coverage >= 80%
- Mock all external dependencies

```python
import pytest
from pathlib import Path

@pytest.mark.asyncio
async def test_process_item_returns_result(tmp_path):
    processor = ItemProcessor(tmp_path)
    result = await processor.process({"name": "test"})
    assert result is not None
    assert result.status == "completed"
```

### Mock External APIs

**ALWAYS mock:**
- LLM APIs (litellm, openai, anthropic) — `unittest.mock.patch`
- External HTTP APIs — `unittest.mock.AsyncMock`
- Schedulers — `unittest.mock.MagicMock`
- File system — `tmp_path` fixture

**NEVER call real APIs in tests.**

```python
from unittest.mock import patch, MagicMock, AsyncMock

@pytest.fixture
def mock_llm():
    with patch("myapp.core.llm.acompletion") as mock:
        mock.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="response"))]
        )
        yield mock

@pytest.fixture
def mock_context(tmp_path):
    context = MagicMock()
    context.logger = MagicMock()
    context.config = MagicMock()
    return context
```

### Test Organization

```
<project>/
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # Shared fixtures
│   ├── test_<module>.py
│   └── fixtures/            # Test data
│       └── sample_data/
```

### Async Tests

```python
import pytest

@pytest.mark.asyncio
async def test_async_function():
    result = await some_async_function()
    assert result is not None
```

Configure in `pyproject.toml`:
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

### Code Quality Checks

**ALWAYS run before commit:**

```bash
# Lint check
uv run ruff check <src_dir>/

# Format check
uv run ruff format --check <src_dir>/
```

### Running Tests

Before every commit:

```bash
# Code quality (MUST pass)
uv run ruff check <src_dir>/

# Unit tests with coverage
uv run pytest tests/ --cov=<src_dir> --cov-fail-under=80

# All tests
uv run pytest --cov=<src_dir> --cov-fail-under=80
```

### CI/CD Gate

**Tests MUST pass in CI before merge.**

All PRs require:
- [ ] `ruff check` passing (no lint errors)
- [ ] Unit tests passing
- [ ] Coverage >= 80%
- [ ] No warnings or errors
