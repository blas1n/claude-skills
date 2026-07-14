---
name: mcp-remote-tools-attach-race
description: 코딩 CLI(claude code 등)에 원격 HTTP MCP 서버로 툴을 주입할 때, CLI가 MCP 연결을 기다리지 않고 턴을 시작해 에이전트가 "툴 0개"로 돌아간다. env var를 unset 하는 건 고치는 게 아니다(기본값이 이미 non-blocking). 트리거: system/init의 mcp_servers status=pending, tools=[], 에이전트가 툴을 ToolSearch로 찾음, 툴 없이 답을 지어냄.
---

# 원격 MCP 툴은 턴 시작에 늦는다 — 그리고 `unset != false`

## Problem

CLI를 "우리 툴만 쓰는 에이전트"로 만드는 구성:

```
claude --print --strict-mcp-config --mcp-config '{"mcpServers":{"x":{"type":"http",...}}}' \
       --allowedTools "mcp__x__*" --disallowedTools "<네이티브 전부>"
```

- **증상**: `system/init`에 `mcp_servers: [{status: "pending"}]`, `tools: []`.
  네이티브는 막혔고 우리 툴은 아직 안 붙었다 → **에이전트의 툴이 0개**.
- **근본 원인**: CLI가 **MCP 연결을 기다리지 않고 턴을 시작**한다.
  `MCP_CONNECTION_NONBLOCKING`의 **기본값이 이미 non-blocking**이다.
- **흔한 오해 (내가 한 실수)**:
  1. "오퍼레이터 셸의 `MCP_CONNECTION_NONBLOCKING=true`가 문제니 `env.pop()` 하면 된다"
     → **완전한 no-op**. unset은 false가 아니다. 기본값이 이미 나쁜 값이다.
  2. "MCP 툴이 `ToolSearch` 뒤로 deferred 되는 건 **툴 개수 임계치** 때문이다"
     → 아니다. **늦은 연결의 증상**이다. blocking connect면 86개도 eager로 붙는다.
     `ToolSearch`를 허용해서 "고치면" 안 된다.

## Solution

**명시적으로 `false`를 넣어라.** pop 하지 말고.

```python
env = sanitized_subprocess_env()
env["MCP_CONNECTION_NONBLOCKING"] = "false"   # unset != false
```

측정 결과 (동일 플래그, env만 다름):

| env | mcp_servers | init의 tools | 에이전트 행동 |
|---|---|---|---|
| unset (기본) | `pending` | 0 | **답을 지어냄** ("빈 디렉터리인 것 같습니다") |
| `=false` | **connected** | **9** | 진짜 툴 호출 → 진짜 결과 |

### 진단 recipe — `env -i`로 프로브하라

**내 프로브는 오염돼 있었다.** Claude Code 세션 *안에서* CLI를 띄우면
`CLAUDECODE=1`, `CLAUDE_CODE_ENABLE_TASKS` 등이 상속돼 **툴 노출 집합이 달라진다**
(launchd/데몬이 보는 것과 다름). 데몬이 보는 걸 재현하려면:

```bash
echo "hi" | env -i PATH="$PATH" HOME="$HOME" \
  claude --print --output-format stream-json --verbose --setting-sources "" \
  --strict-mcp-config --mcp-config "$MCP" --disallowedTools "$NATIVE" \
| python3 -c 'import sys,json
for l in sys.stdin:
    e=json.loads(l)
    if e.get("type")=="system" and e.get("subtype")=="init":
        print(e["mcp_servers"], sorted(e["tools"])); break'
```

로컬 stdio MCP는 즉시 연결돼 이 버그를 **숨긴다**. 반드시 **원격/지연이 있는 HTTP**로
재현하라 (로컬 HTTP 서버에 `time.sleep(0.6)`을 넣어 원격을 흉내내면 결정적으로 격리된다).

## Key Insights

- **`unset != false`.** 벤더 CLI/SDK의 기본값이 이미 "나쁜 값"이면, 환경변수를 **지우는** 것은
  아무것도 고치지 않는다. 이 클래스의 버그는 유닛테스트로 절대 안 잡힌다 —
  `env.pop()`은 테스트에서 완벽하게 "동작"한다.
- **deferral/lazy-loading은 대개 타이밍의 증상**이다. 원인(연결 경합)을 고치면 사라진다.
  증상(ToolSearch 차단)을 우회하려 들면 보안 표면을 다시 연다.
- CLI를 프로브할 때 **자기 자신의 세션 env가 결과를 바꾼다**. 데몬 컨텍스트(`env -i`)로 재현하라.
  → [[launchd-daemon-cli-keychain-auth-fallback]]과 같은 계열의 함정.

## Red Flags

- `system/init`에 `status: "pending"` / `tools: []`인데 그냥 넘어간다.
- 에이전트가 첫 턴에 `ToolSearch`로 "우리 툴"을 찾고 있다 → 툴이 eager로 안 붙었다는 신호.
- 에이전트가 툴 호출을 **prose로** 뱉는다 (`<invoke name="glob">` 같은 텍스트).
- 로컬(stdio)에선 되는데 배포(원격 HTTP)에서만 "툴이 없다"고 한다.
- 수정이 `env.pop(...)` / `del os.environ[...]` 형태다 → 기본값을 확인했는가?
