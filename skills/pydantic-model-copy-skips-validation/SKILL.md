---
name: pydantic-model-copy-skips-validation
description: pydantic v2 `model_copy(update=...)` does NOT validate — a str passed for a SecretStr (or any coerced type) stays a str and breaks `.get_secret_value()` deep inside the app. Trigger - test fixtures that derive Settings with model_copy, AttributeError 'str' object has no attribute 'get_secret_value', overriding pydantic-settings in tests.
---

# pydantic `model_copy(update=)` skips validation

## Problem

- 증상: a test fixture builds settings with `settings.model_copy(update={"api_secret": "x"})`; the app fails far from the fixture with `AttributeError: 'str' object has no attribute 'get_secret_value'` (or a `Path` field that is a str, an int that is a str…).
- 근본 원인: `model_copy(update=...)` assigns the values as given — no validation, no coercion. The constructor would have turned `"x"` into `SecretStr("x")`; the copy does not.
- 흔한 오해: "the field is typed SecretStr, so it is one". Every test failed at once, which looks like an app bug, not a fixture bug.

## Solution

1. In the update dict, pass the already-typed value: `{"api_secret": SecretStr("x"), "db_path": Path(...)}` and comment why.
2. Or rebuild: `Settings(**{**settings.model_dump(), "api_secret": "x"}, _env_file=None)` — validated, but `model_dump()` turns SecretStr into masked text, so re-supply secrets explicitly.
3. Or `Settings.model_validate({...})` for a fresh validated object.

## Key Insights

- `model_copy` is a shallow struct copy, not a constructor. Anything that relies on validators (coercion, SecretStr wrapping, custom validators) is skipped.
- When many tests fail with a type error from production code right after a new fixture, suspect the fixture's object construction first.
