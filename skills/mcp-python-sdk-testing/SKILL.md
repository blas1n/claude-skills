---
name: mcp-python-sdk-testing
description: "Test mcp Python SDK servers without spawning subprocesses — extract registered handlers from server.request_handlers and invoke ListToolsRequest/CallToolRequest objects directly. Result is wrapped in ServerResult.root."
version: 1.0.0
triggers:
  - pattern: "writing tests for an mcp.server.Server, asking how to assert tools/list or tools/call output without stdio plumbing"
category: test
---

# Testing mcp Python SDK servers

## The setup

The official `mcp` Python SDK (`pip install mcp`, ≥1.0) registers
tools with decorators on a `Server` instance:

```python
from mcp.server import Server
from mcp.types import TextContent, Tool

server = Server("bsage")

@server.list_tools()
async def _list_tools() -> list[Tool]:
    return [...]

@server.call_tool()
async def _call_tool(name: str, arguments: dict) -> list[TextContent]:
    ...
```

The transport (stdio/SSE/etc.) feeds JSON-RPC requests in. For tests
you don't need a transport — just invoke the registered handlers
directly. But the SDK's API for that isn't documented well, so it's
trial-and-error the first time.

## The pattern

After `build_server(...)` runs the decorators, the server stores
handlers in `server.request_handlers`, **keyed by the Pydantic
request class**, not by method name. Construct the request object
yourself and call:

```python
import json
import pytest
from mcp.types import CallToolRequest, CallToolRequestParams, ListToolsRequest


@pytest.mark.asyncio
async def test_list_tools(state):
    server = build_server(state)
    handler = server.request_handlers[ListToolsRequest]
    req = ListToolsRequest(method="tools/list", params=None)
    result = await handler(req)
    # result is mcp.types.ServerResult, with the actual response on .root
    tools = result.root.tools
    names = {t.name for t in tools}
    assert "search_knowledge" in names


@pytest.mark.asyncio
async def test_call_tool(state):
    server = build_server(state)
    handler = server.request_handlers[CallToolRequest]
    params = CallToolRequestParams(name="search_knowledge", arguments={"query": "x"})
    req = CallToolRequest(method="tools/call", params=params)
    result = await handler(req)
    content = result.root.content
    assert content[0].type == "text"
    payload = json.loads(content[0].text)  # tools that return dicts get JSON-encoded
    assert "results" in payload
```

## Things easy to get wrong

- **Don't `getattr(server, '_list_tools_handler', ...)`**. There's no
  per-decorator attribute. Everything goes into the
  `request_handlers` dict.
- **Don't pass `name="tools/list"` directly to a handler**. It expects
  the typed request object. The dispatcher inside `Server.run` does
  the JSON→typed conversion; in tests you skip the dispatcher.
- **The result wraps in `ServerResult.root`**, not at the top level.
  Reaching for `result.tools` returns `None` or raises depending on
  SDK version. Always go through `.root`.
- **`call_tool` handlers can return `list[TextContent]` OR a dict for
  `structuredContent`**. The SDK builds the `CallToolResult` for you.
  The `content` you assert on is always under `result.root.content`.

## When to use a subprocess instead

Subprocess testing (`mcp.client.stdio.stdio_client`) is right for
end-to-end smoke — confirm the entry point, the JSON-RPC framing,
and stderr/stdout separation all work together. But it's slow and
stdout-protocol corruption (e.g. a stray `print` in startup code)
shows up as cryptic decode errors rather than a useful message.

For unit-level coverage of tool dispatch, registration, and
behavior, the in-process pattern above is faster and gives clearer
failure messages. Keep one subprocess smoke per branch + many
in-process unit tests for the dispatch logic.

## Stdout-corruption guard for stdio servers

When you do run an stdio MCP server (production or subprocess test),
anything that writes to stdout outside the JSON-RPC channel will
corrupt the client's parser. The most common culprit: `structlog`
defaulting to stdout. Re-bind logging to stderr **before** the server
starts:

```python
import logging, sys, structlog

def _configure_stdio_logging():
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.INFO)
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    structlog.configure(
        processors=[structlog.processors.JSONRenderer()],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
```

Call it at the top of the stdio entry point, before any `import`
that might initialize logging on its own.
