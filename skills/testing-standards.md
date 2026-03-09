---
name: testing-standards
description: Common testing guidelines, mock patterns, and coverage standards for Python projects
---

# Testing Standards Skill

## Test Structure

```
<project>/
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # Shared fixtures
│   ├── test_<module>.py     # Unit tests
│   └── fixtures/            # Test data files
```

## Test Types

### Unit Tests

**Purpose**: Test individual functions/classes with mocked dependencies

```python
import pytest
from pathlib import Path

@pytest.mark.asyncio
async def test_process_returns_result(tmp_path):
    processor = DataProcessor(tmp_path)
    result = await processor.process({"input": "test"})
    assert result is not None
    assert result.status == "success"
```

**Coverage target**: 80%+

---

### Mock Patterns

#### Mock External APIs (AsyncMock)

```python
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.fixture
def mock_api_client():
    client = AsyncMock()
    client.fetch = AsyncMock(return_value={"data": "test"})
    client.send = AsyncMock(return_value=True)
    return client
```

#### Mock LLM Calls

```python
@pytest.fixture
def mock_llm():
    with patch("myapp.core.llm.acompletion") as mock:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Processed response"
        mock.return_value = mock_response
        yield mock
```

#### Mock File System (tmp_path)

```python
@pytest.fixture
def mock_workspace(tmp_path):
    """Use tmp_path for file system tests."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return tmp_path
```

#### Mock Context Object

```python
@pytest.fixture
def mock_context(tmp_path):
    context = MagicMock()
    context.logger = MagicMock()
    context.config = MagicMock()
    context.credentials = MagicMock()
    return context
```

---

### Async Tests

```python
import pytest

@pytest.mark.asyncio
async def test_async_function():
    result = await some_async_function()
    assert result is not None
```

**Configure in `pyproject.toml`:**
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

---

## Coverage Requirements

**Minimum**: 80% across all modules

**Check coverage:**
```bash
uv run pytest tests/ --cov=<src_dir> --cov-report=html
open htmlcov/index.html
```

---

## Critical Testing Rules

1. **Never call real APIs in tests** (LLM, HTTP, database connections, schedulers)
2. **Always mock external services** with `unittest.mock.patch` or `AsyncMock`
3. **Test error paths** alongside happy paths
4. **Use `tmp_path` pytest fixture** for temporary test files
5. **Clean up after tests** (pytest handles `tmp_path` cleanup automatically)
6. **Use `asyncio_mode = "auto"`** to avoid `@pytest.mark.asyncio` on every test
7. **Test edge cases** — empty inputs, None values, boundary conditions
8. **Test validation** — invalid inputs should raise appropriate errors
