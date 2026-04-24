---
name: litellm-tool-call-provider-probe
description: Before writing LiteLLM tool-calling code, run a 10-line probe that asserts tool_calls actually populate for your model+provider combo — some prefixes silently drop the tools parameter.
version: 1.0.0
task_types: [coding, debugging]
---

# LiteLLM tool-calling: probe the provider before you trust it

## The trap

LiteLLM exposes one unified `acompletion(tools=[...])` surface but routes to many
provider-specific backends under the hood. **Some backends silently drop the
`tools` parameter** and just run a text-completion — you get an empty
`message.content`, `message.tool_calls == None`, no warning, no error.

Integration tests that mock `litellm.acompletion` will pass. Unit tests will pass.
A whole tool-calling loop will execute and emit `tools_invoked=0` for every run
until someone notices the workspace is empty.

## Confirmed cases (2026-04)

- `ollama/<model>` → routes to Ollama `/api/generate`, **drops tools**.
  Use `ollama_chat/<model>` (routes to `/api/chat`) for tool calling.
- Any provider without a native chat-completions endpoint may behave this way.
  Check the LiteLLM provider docs for `/v1/chat/completions` or equivalent.

## The 10-line probe

Before writing any production code that assumes tool calls work, do this:

```python
import asyncio, litellm, json

async def main():
    r = await litellm.acompletion(
        model="<your/model>",
        api_base="<your base url>",
        messages=[
            {"role": "system", "content": "Use the echo tool to reply."},
            {"role": "user", "content": "say hi"},
        ],
        tools=[{
            "type": "function",
            "function": {
                "name": "echo",
                "description": "Echo a message back",
                "parameters": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            },
        }],
        tool_choice="auto",
        temperature=0.1,
    )
    msg = r.choices[0].message
    print("content:", repr(getattr(msg, "content", None)))
    print("tool_calls:", getattr(msg, "tool_calls", None))

asyncio.run(main())
```

**Pass criterion**: `tool_calls` is a non-empty list with at least one entry
whose `function.name == "echo"`. If it's `None` or `[]` and `content` is a
short prose reply instead of the tool call, your prefix is wrong — investigate
before writing more code.

## When to run

- **Before** integrating a new LLM model into any tool-calling pipeline.
- **After** switching providers (Ollama → vLLM, OpenAI → BSGateway, etc.).
- **When** unit tests pass but live runs produce `files_written=0` /
  `tools_invoked=0` or empty output.

## If the probe fails

1. Bypass LiteLLM — call the provider's native API directly with the same tools
   payload. If that works, the issue is the LiteLLM provider mapping, not the
   model.
2. Check LiteLLM docs / source for alternative provider prefixes
   (`ollama_chat`, `openai`, `azure`, etc.).
3. Check the provider's own docs: which endpoint supports function calling?
   Match your LiteLLM prefix to that endpoint.

## Related symptoms to watch for

- `run_llm_completed tools_invoked=0` repeatedly for a model that you *know*
  supports tools.
- `output_ref.inline == ""` across a whole chain of runs.
- `completion_tokens` > 0 but `content` is empty — indicates the model replied
  to what it saw, which may have been a request without tools.

The lesson: **unit tests that mock `litellm.acompletion` prove nothing about
whether the real provider wires tools through**. Always probe before shipping.
