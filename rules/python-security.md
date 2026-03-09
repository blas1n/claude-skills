---
description: Common security rules for all Python projects
---

# Security Rules

## CRITICAL: Credential, Data, and Safety Security

### 1. Environment Variables

**NEVER commit secrets to git.**

**ALWAYS use .env files (gitignored) + pydantic-settings:**

```python
# Correct
from myapp.core.config import settings
# settings.api_key is auto-loaded from .env via pydantic-settings

# Wrong
API_KEY = "sk-ant-..."  # NEVER hardcode credentials!
```

**Provide .env.example (committed, no real secrets):**

```bash
# .env.example (committed)
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/mydb
API_KEY=
DEBUG=false

# .env (gitignored, actual secrets)
API_KEY=sk-real-key-here
```

### 2. Credentials in Logs

**NEVER log or expose authentication tokens.**

```python
# Correct
logger.info("credential_loaded", service=name)

# Wrong
logger.info(f"Authenticated with token: {token}")  # NO!
```

### 3. API Keys in Logs

**NEVER log API keys or secrets.**

```python
# Correct
logger.info("api_call", endpoint=url, model=settings.model_name)

# Wrong
logger.info(f"Using API key: {settings.api_key}")  # NO!
```

### 4. Temporary File Cleanup

**ALWAYS clean up temporary files after processing.**

```python
# Correct
try:
    await process_data(tmp_dir)
finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)

# Wrong — leave temp files
pass  # tmp files remain
```

### 5. Secure Defaults

**Principle of least privilege:**

- API keys scoped to minimum permissions
- No `shell=True` in subprocess calls
- Default to restrictive settings
- File permissions minimal

### 6. Error Messages

**NEVER expose credentials in error messages:**

```python
# Correct (user-facing)
raise AuthenticationError("Invalid credentials for service 'calendar'")

# Correct (logs)
logger.error("auth_failed", service=name, exc_info=True)

# Wrong
raise Exception(f"Auth failed with token {token}")  # Exposes secrets!
```

### 7. Input Validation

**Validate all external inputs:**

```python
# Pydantic for API inputs
from pydantic import BaseModel, Field

class CreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    model_config = {"extra": "forbid"}

# Regex for identifiers
import re
def validate_name(name: str) -> str:
    if not re.match(r'^[a-z][a-z0-9-]*$', name):
        raise ValueError(f"Invalid name: {name}")
    return name
```

## Verification Checklist

Before every commit:
- [ ] No hardcoded credentials (API keys, tokens)
- [ ] .env.example provided with all keys (no real values)
- [ ] No secrets in logs or error messages
- [ ] Sensitive directories in .gitignore (.env, .credentials/, data/)
- [ ] Temp file cleanup implemented (try/finally)
- [ ] No `shell=True` in subprocess calls
- [ ] All external inputs validated
