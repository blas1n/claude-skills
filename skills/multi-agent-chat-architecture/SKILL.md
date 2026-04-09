---
name: multi-agent-chat-architecture
description: Multi-agent chat architecture patterns — synchronous chatbot vs async dispatch, agent routing evolution, SSE real-time delivery
version: 1.0.0
task_types: [design, coding]
triggers:
  - pattern: "building multi-agent chat, agent routing, or converting synchronous chat to async"
---

# Multi-Agent Chat Architecture

Hard-won patterns from building a multi-agent "AI Company" chat system.

## Trap 1: Synchronous Multi-Agent Chat Hits Timeouts

**Assumption**: Call each mentioned agent sequentially in one HTTP request, return all responses.

**Reality**: Each agent call takes 15-30s (worker CLI or LLM API). 3+ agents = 45-90s, exceeding typical HTTP timeouts (120s). Users see timeouts while agents are still working.

**Solution**: Fire-and-forget dispatch pattern.

```
POST /chat → store user msg → dispatch N agents as background tasks → return immediately
Background: each agent works independently → stores result → publishes SSE event
Frontend: EventSource receives each response as it arrives
```

Key implementation details:
- Each background task gets its own DB session (`async with async_session() as db:`)
- Reload project + agents fresh in each task (request session is closed)
- `asyncio.create_task()` for each agent — truly parallel execution
- Delegation chains: if agent A's response @mentions agent B, spawn another background task
- Depth limit (3) prevents infinite delegation loops

```python
# Return type changes from ChatResponse to ChatDispatchResponse
class ChatDispatchResponse(BaseModel):
    dispatched_agents: list[str]  # Just names — responses arrive via SSE
```

## Trap 2: Static Keyword Routing Breaks With Custom Templates

**Evolution of wrong approaches**:
1. Hardcoded role-keyword mapping → breaks when user customizes agent names/roles
2. Bilingual synonym dictionary → maintenance nightmare, doesn't scale to new languages
3. Per-agent `routing_keywords` field → extra schema complexity, users forget to fill it

**Key insight**: Don't fight the routing problem with static rules. Use existing LLM infrastructure (the worker that's already running) to make routing decisions. The org-chart root's executor can classify messages using conversation context — no extra API keys, no new infrastructure.

**Final pattern**:
1. Explicit @mentions → use directly (user intent is clear)
2. No mention → dispatch to org root's worker with a routing-only prompt
3. Worker fails → fallback to org chart root agent

The routing call is internal infrastructure — NOT stored in chat, NOT published to SSE.

## Trap 3: Redis Streams Double Serialization

**Scenario**: `publish()` JSON-encodes dict/list fields. `consume()` auto-decodes ALL fields via `json.loads()`. If a field was already `json.dumps()`'d by the producer, consume decodes it back to the original type.

```python
# Producer: history is json.dumps(list) → string "[ {...} ]"
data = {"history": json.dumps(history)}  # → stored as string in Redis

# Consumer: json.loads(string) → list again!
parsed["history"] = json.loads(value)  # → list, not string

# Pydantic model expects string → ValidationError
WorkerTaskMessage(history=parsed["history"])  # 💥 Input should be a valid string
```

**Fix**: Re-serialize at the consumer boundary if the schema expects a string.

## Pattern: SSE for Real-Time Chat (Not Polling)

**Stack**: Redis Streams → SSE endpoint → EventSource → React Query cache patch

- **Publish**: Every stored message → `XADD chat:events:{project_id}`
- **SSE tail**: `XREAD` with `$` (new messages only), no consumer group needed
- **Frontend**: `useChatEvents(projectId)` hook → `setQueryData` on React Query cache
- **No polling**: EventSource handles reconnect with exponential backoff

Events: `message_created`, `history_cleared`, `agent_status` (busy/online).

This same stream architecture extends to Slack/Telegram adapters — they're just additional consumers of the same Redis Stream.

## Pattern: Optimistic UI Deduplication

When SSE delivers the real message before the HTTP response returns, both the optimistic bubble and the real message show. Fix with **derived state, not effects**:

```typescript
const showPendingUser = useMemo(() => {
  if (!pendingMessage) return false
  return !messages.some((m) => m.role === 'user' && m.content === pendingMessage)
}, [messages, pendingMessage])
```

For multi-agent typing indicators, track per-agent:

```typescript
const activeTypingAgents = useMemo(() => {
  const responsesAfter = messages.slice(lastUserIdx + 1)
  const respondedNames = new Set(responsesAfter.filter(m => m.role === 'assistant').map(m => m.agent_name))
  return pendingAgents.filter(name => !respondedNames.has(name))
}, [messages, pendingMessage, pendingAgents])
```
