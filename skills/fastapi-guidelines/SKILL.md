---
name: fastapi-guidelines
description: FastAPI backend development guidelines. Domain-Driven Design with Router→Service→Repository layering, SQLModel/SQLAlchemy ORM, async patterns, Pydantic validation, error handling, and TestClient testing.
version: 1.0.0
task_types: [coding, refactor]
required_tools: [Read, Edit, Write, Bash]
triggers:
  - pattern: "code imports fastapi or user asks about FastAPI development"
---

# FastAPI Backend Development Guidelines

## Purpose

Comprehensive guide for modern FastAPI development with async Python, emphasizing Domain-Driven Design, layered architecture (Router → Service → Repository), SQLModel ORM, and async best practices.

## When to Use This Skill

- Creating new API routes or endpoints
- Building domain services and business logic
- Implementing repositories for data access
- Setting up database models with SQLModel
- Async/await patterns and error handling
- Organizing backend code with DDD
- Pydantic validation and DTOs
- Testing FastAPI routes with TestClient

---

## Layered Architecture

**Three-Layer Pattern:**
1. **Router Layer**: API endpoints, request validation, response formatting
2. **Service Layer**: Business logic, orchestration, domain rules
3. **Repository Layer**: Data access, queries, database operations

**Rules:**
- Routers call Services (never Repositories directly)
- Services orchestrate business logic
- Repositories handle all database operations
- Async/await throughout the stack

---

## Project Structure

```
<project>/
  <src>/
    main.py                  # FastAPI app creation with lifespan
    api/
      v1/
        routers/             # API route handlers by domain
    domain/                  # Domain-Driven Design
      <domain>/
        model.py             # SQLModel database models
        repository.py        # Data access layer
        service.py           # Business logic layer
      shared/
        base_repository.py   # Generic BaseRepository
    dtos/                    # Pydantic request/response DTOs
    db/
      orm.py                 # Session management
    core/
      config.py              # Pydantic Settings
    middleware/               # Error handling, auth
    error/                   # Custom exception classes
```

---

## Router Pattern

```python
from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

router = APIRouter(prefix="/items", tags=["items"])

@router.get("/{item_id}")
async def get_item(
    item_id: str,
    session: AsyncSession = Depends(get_read_session),
) -> ItemResponse:
    service = ItemService(session)
    return await service.get_item(item_id)

@router.post("", status_code=201)
async def create_item(
    request: ItemCreateRequest,
    session: AsyncSession = Depends(get_write_session),
) -> ItemResponse:
    service = ItemService(session)
    return await service.create_item(request)
```

---

## Model Pattern (SQLModel)

```python
from sqlmodel import SQLModel, Field, Column, DateTime, Text
from datetime import datetime, timezone
from typing import Optional
from ulid import ULID

def generate_item_id() -> str:
    return f"item_{ULID()}"

class Item(SQLModel, table=True):
    __tablename__ = "item"

    id: str = Field(
        default_factory=generate_item_id,
        primary_key=True,
        max_length=30,
    )
    name: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
        default_factory=lambda: datetime.now(tz=timezone.utc),
    )
    # Soft delete pattern
    deleted_at: Optional[datetime] = Field(
        sa_column=Column(DateTime(timezone=True), nullable=True),
        default=None,
    )
```

---

## Repository Pattern

```python
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

class ItemRepository(BaseRepository[Item]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Item)

    async def find_by_name(self, name: str) -> Optional[Item]:
        stmt = select(Item).where(
            Item.name == name,
            Item.deleted_at.is_(None),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
```

---

## Service Pattern

```python
from sqlmodel.ext.asyncio.session import AsyncSession

class ItemService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self._repository = ItemRepository(session)

    async def get_item(self, item_id: str) -> ItemResponse:
        item = await self._repository.get_by_id(item_id)
        if not item:
            raise NotFoundError(f"Item {item_id} not found")
        return ItemResponse.model_validate(item)

    async def create_item(self, request: ItemCreateRequest) -> ItemResponse:
        item = Item(name=request.name)
        self.session.add(item)
        await self.session.commit()
        await self.session.refresh(item)
        return ItemResponse.model_validate(item)
```

---

## DTO Pattern (Pydantic)

```python
from pydantic import BaseModel, Field, field_validator
from datetime import datetime

class ItemResponse(BaseModel):
    id: str
    name: str
    created_at: datetime

class ItemCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    model_config = {"extra": "forbid"}  # Reject unknown fields
```

---

## Error Handling

```python
# Custom exceptions
class AppException(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)

class NotFoundError(AppException):
    pass

class ForbiddenError(AppException):
    pass

class UnauthorizedError(AppException):
    pass

# ErrorHandlerMiddleware maps exceptions to HTTP responses:
# NotFoundError → 404, ForbiddenError → 403, UnauthorizedError → 401
```

---

## Async Patterns

```python
import asyncio

# Parallel queries with asyncio.gather
async def get_dashboard_data(self) -> dict:
    total, monthly, today = await asyncio.gather(
        self._get_total_count(),
        self._get_monthly_count(),
        self._get_today_count(),
    )
    return {"total": total, "monthly": monthly, "today": today}
```

---

## Testing FastAPI Routes (TestClient)

```python
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def client(app):
    return TestClient(app)

def test_get_item_success(client):
    response = client.get("/api/v1/items/test-id")
    assert response.status_code == 200
    assert response.json()["id"] == "test-id"

def test_create_item_success(client):
    response = client.post(
        "/api/v1/items",
        json={"name": "New Item"},
    )
    assert response.status_code == 201
    assert response.json()["name"] == "New Item"

def test_get_item_not_found(client):
    response = client.get("/api/v1/items/nonexistent")
    assert response.status_code == 404

# Async route testing with pytest-asyncio
@pytest.mark.asyncio
async def test_service_layer_directly():
    mock_session = AsyncMock()
    service = ItemService(mock_session)
    # ... test service logic
```

---

## Core Principles

1. **Layered Architecture**: Router → Service → Repository (never skip layers)
2. **Domain-Driven Design**: Organize by domain, not by type
3. **Async Everything**: Use async/await throughout the stack
4. **Repository Pattern**: All data access through repositories
5. **Service Layer**: Business logic in services, not routers or repositories
6. **DTOs for API**: Use Pydantic DTOs for request/response (separate from models)
7. **Type Hints**: Explicit types on all functions and parameters
8. **Error Handling**: Custom exceptions + middleware for HTTP mapping
9. **Dependency Injection**: Use FastAPI's `Depends()` for sessions
10. **Soft Delete**: Use `deleted_at` timestamp instead of hard deletes
11. **N+1 Prevention**: Use `asyncio.gather` and DataLoader patterns for parallel queries
