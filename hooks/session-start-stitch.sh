#!/usr/bin/env bash
# SessionStart hook: auto-register stitch MCP in ~/.claude.json if missing

CLAUDE_JSON="$HOME/.claude.json"
STITCH_ENTRY='{"command":"npx","args":["-y","stitch-mcp-auto"],"env":{"GOOGLE_CLOUD_PROJECT":"bsvibe"}}'

if [ ! -f "$CLAUDE_JSON" ]; then
    echo "{\"mcpServers\":{\"stitch\":$STITCH_ENTRY}}" > "$CLAUDE_JSON"
    echo '{"systemMessage":"[Stitch MCP] Registered. Please restart Claude Code for MCP to connect."}'
    exit 0
fi

python3 - <<EOF
import json, sys

with open("$CLAUDE_JSON") as f:
    d = json.load(f)

if "stitch" not in d.get("mcpServers", {}):
    d.setdefault("mcpServers", {})["stitch"] = {
        "command": "npx",
        "args": ["-y", "stitch-mcp-auto"],
        "env": {"GOOGLE_CLOUD_PROJECT": "bsvibe"}
    }
    with open("$CLAUDE_JSON", "w") as f:
        json.dump(d, f)
    print('{"systemMessage":"[Stitch MCP] Registered. Please restart Claude Code for MCP to connect."}')
EOF
