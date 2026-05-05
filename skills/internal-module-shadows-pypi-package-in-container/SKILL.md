---
name: internal-module-shadows-pypi-package-in-container
description: A project's src/<name>/ folder named the same as a PyPI package (mcp, jwt, click, …) silently shadows the PyPI install in production container layouts where local dev resolves correctly. Symptom — works on `pytest` and `uvicorn` locally, fails on first import in prod with `cannot import name X from <pkg>`.
version: 1.0.0
task_types: [debugging, devops]
---

# Internal module shadows a same-named PyPI package in containers

## Symptom

```
ImportError: cannot import name 'ClientSession' from 'mcp'
(/usr/local/lib/python3.11/site-packages/mcp/__init__.py)
```

Works locally with `pytest`, `uvicorn`, `python -m`. Fails on the
first real request in the production container — *only* in the code
path that triggers the shadowed import.

## Cause

The repo defines its own `backend/src/<pkg-name>/` (or
`src/<pkg-name>/`) module that **happens to share a name with a PyPI
package** the project also depends on (`mcp`, `jwt`, `click`,
`google`, `parser`, `cli`, `auth`…).

In local dev, both live on `sys.path` but the order
(`backend/src/` first, then `.venv/lib/.../site-packages/`) means
`import <name>` resolves to the project module — and that's fine
because either:
- The codebase only uses deep paths (`from mcp.client.session import
  ClientSession`), so the shadow doesn't matter
- The CI test surface patches the import boundary

In the production container build, `uv pip install --system .` (or
`pip install -e .`) installs the project's `src/<name>/` *into*
`site-packages/` directly. Now both the PyPI `<name>/` and the
project's `<name>/` claim `/usr/local/lib/python3.11/site-packages/<name>/`,
and the project wins. PyPI `<name>` is fully installed (`pip show
<name>` reports its version) but `import <name>` resolves to the
shadowed `__init__.py` that exports the project's symbols only.

## How the test surface misses this

Unit tests of the consuming module (in our case
`test_direct_llm_adapter.py`) patched the `_mcp_session` context
manager wholesale, so the body containing
`from mcp import ClientSession` never executed. The live-LLM smoke
test passed `mcp_servers=None`, which short-circuits before the
import. **Both the high-coverage unit tier AND the
pseudo-integration smoke tier had the import path patched out or
gated off.**

100% green tests + `coverage` reports that include the import line as
"covered" (because `pytest` imported the module at collection time)
*can still ship a broken import* if the only real exercise of the
line is the import itself, and the code path that triggers the
import is always mocked.

## Diagnosis (60-second triage)

When you see `ImportError` from a name you know is installed:

```bash
docker exec <container> python3 -c "
import <name>, importlib.metadata as m
print('resolved:', <name>.__file__)
print('installed:', m.version('<name>'))
print('attrs:', sorted(x for x in dir(<name>) if not x.startswith('_'))[:15])
"
```

If the resolved `__file__` is `/usr/local/lib/python3.11/site-packages/<name>/__init__.py`
**but** `attrs` shows your project's symbols (not the SDK's), it's
the shadow. If the SDK has a deeper sub-package
(`<name>.client.session`), `from <name>.<sub> import X` still works
— the shadow only blocks top-level `__init__.py` re-exports.

## Fix

**Always** use the deep import path for the SDK type. The deeper
path is always unambiguous because the project's `<name>/__init__.py`
doesn't claim the sub-paths.

```python
# Wrong — shadowed in container
from mcp import ClientSession

# Right — deep path always resolves to the SDK
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client
```

## Regression test (lock the import path)

The unit tests that patch out the import won't catch a regression to
the shadowed form. Add a small test that imports the SDK type via
the deep path and asserts it's a class/callable:

```python
def test_<sdk>_<symbol>_imports_from_sdk_not_internal_module() -> None:
    """Pin the deep import path. Project's ``src/<name>/`` shadows
    PyPI <name> in container site-packages — top-level
    ``from <name> import <symbol>`` would silently break in prod."""
    from <name>.<sub>.<module> import <symbol>
    assert isinstance(<symbol>, type)  # or callable(...)
```

The test runs in dev too — its job is to *fail* the next time someone
shortens the import. Local dev resolution doesn't matter; what
matters is that a future contributor reads this test and doesn't
revert the deep path.

## Better defenses (if you can afford them)

- **Rename the internal module** so it never collides with a PyPI
  package. `src/mcp_server/` instead of `src/mcp/` removes the
  shadow risk entirely. Best long-term fix; expensive once the
  shadowed name is wired through imports across the codebase.
- **Boundary integration test** — fire a real request that exercises
  the import path with no patches. Catches a wider class of
  "100% green tests, broken in prod" bugs than this specific shadow.
- **Container-image smoke test** — `docker exec ... python -c "from
  <name>.<sub> import <symbol>"` as part of the build pipeline.
  Trivial, but only catches the symbols you explicitly check.

## When to suspect this

- Project has `src/<name>/` AND `<name>` listed in pyproject deps
- Error says `cannot import name X from <pkg>` and X *definitely*
  exists in the PyPI version on your dev machine
- Local dev is fine, container fails on first use
- `pip show <pkg>` reports the right version but `python -c "import
  <pkg>; print(dir(<pkg>))"` shows the wrong attrs

If two of those four are true, run the diagnostic command and
confirm before changing anything else.
