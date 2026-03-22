#!/usr/bin/env bash
# SessionStart hook: auto-register stitch MCP in ~/.claude.json if missing

CLAUDE_JSON="$HOME/.claude.json"
STITCH_ENTRY='{"command":"npx","args":["-y","stitch-mcp-auto"],"env":{"GOOGLE_CLOUD_PROJECT":"bsvibe"}}'
STITCH_TOKENS="$HOME/.stitch-mcp-auto/tokens.json"
STITCH_CONFIG="$HOME/.stitch-mcp-auto/config.json"

# Ensure stitch auth tokens are properly initialized
# expiry_date:0 is falsy in JS → access_token never refreshed → empty token bug
if [ -f "$STITCH_TOKENS" ]; then
    EXPIRY=$(python3 -c "import json; t=json.load(open('$STITCH_TOKENS')); print(t.get('expiry_date', 0))" 2>/dev/null)
    if [ "$EXPIRY" = "0" ] || [ -z "$EXPIRY" ]; then
        # Fix: set expiry to past (non-zero) so JS refresh condition triggers
        python3 - <<'PYEOF'
import json, os
p = os.path.expanduser("~/.stitch-mcp-auto/tokens.json")
t = json.load(open(p))
t["expiry_date"] = 1  # non-zero past timestamp → triggers refresh on next run
json.dump(t, open(p, "w"), indent=2)
PYEOF
    fi
fi

# Ensure stitch config has setupComplete
if [ ! -f "$STITCH_CONFIG" ] || ! python3 -c "import json; c=json.load(open('$STITCH_CONFIG')); assert c.get('setupComplete')" 2>/dev/null; then
    mkdir -p "$HOME/.stitch-mcp-auto"
    echo '{"projectId":"bsvibe","setupComplete":true}' > "$STITCH_CONFIG"
fi

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
