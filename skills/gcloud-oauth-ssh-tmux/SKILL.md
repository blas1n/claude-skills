---
name: gcloud-oauth-ssh-tmux
description: gcloud OAuth authentication in SSH/headless environments — use tmux to handle interactive browser flow when no local browser is available
---

# gcloud OAuth in SSH/Headless Environments

## The Problem

`gcloud auth application-default login` opens a browser. In SSH environments this fails.
`--no-browser` mode generates a URL and waits for stdin — but naive approaches all fail.

## Why Naive Approaches Fail

### Attempt 1: Pipe callback URL after second invocation → CSRF error

```bash
# WRONG: Running gcloud twice generates DIFFERENT state each time
gcloud auth application-default login --no-browser  # generates state=AAA
# ... user runs remote-bootstrap, gets callback with state=AAA ...
echo "<callback_url>" | gcloud auth application-default login --no-browser  # generates state=BBB
# → "mismatching_state" CSRF error — state=AAA ≠ state=BBB
```

**Root cause**: Each invocation generates a new PKCE challenge + state. The callback URL is bound to the specific session that generated it.

### Attempt 2: FIFO named pipe → blocks or FD lost

```bash
# WRONG: FD opened in one shell is not inherited by background processes in another shell call
mkfifo /tmp/gauth-fifo
exec 3>/tmp/gauth-fifo          # opens write end in THIS shell
gcloud ... < /tmp/gauth-fifo &  # different process, FD 3 not shared
```

**Root cause**: In non-interactive environments (CI, Bash tool, subshells), each command runs in an isolated shell. `exec` FDs don't persist across tool invocations.

## The Working Solution: tmux

Use `tmux new-window` to start gcloud in a persistent interactive session, capture output via `tee`, then feed response with `send-keys` — all from the same tmux server.

```bash
# Step 1: Start gcloud in a tmux window, capture output to file
tmux new-window -n gcloud-auth \
  'gcloud auth application-default login --no-browser 2>&1 | tee /tmp/gauth-out.txt; echo "DONE" >> /tmp/gauth-out.txt'

# Step 2: Wait for it to print the --remote-bootstrap URL
sleep 4
cat /tmp/gauth-out.txt
# Output contains: gcloud auth application-default login --remote-bootstrap="https://accounts.google.com/..."

# Step 3: User runs the --remote-bootstrap command on their LOCAL machine
# This opens a browser, authenticates, outputs: https://localhost:8085/?state=...&code=...

# Step 4: Feed the callback URL to the waiting tmux window
tmux send-keys -t gcloud-auth "<callback_url>" Enter

# Step 5: Verify success
sleep 4
cat /tmp/gauth-out.txt
# Should show: Credentials saved to file: [~/.config/gcloud/application_default_credentials.json]
```

## Complete Flow

```
SSH server (tmux)                    Local machine
─────────────────────────────────    ─────────────────────────
tmux new-window gcloud --no-browser
  → prints --remote-bootstrap URL
                                  ←  copy URL
                                     gcloud auth --remote-bootstrap="<URL>"
                                     browser opens → user logs in
                                     outputs: https://localhost:8085/?...
  tmux send-keys "<callback>"    ←  copy callback URL
  → Credentials saved ✓
```

## After Authentication

```bash
# Set quota project (avoids billing warnings)
gcloud auth application-default set-quota-project <PROJECT_ID>

# For devcontainers: store credentials in ~/.claude/ (already mounted)
mkdir -p ~/.claude/credentials
cp ~/.config/gcloud/application_default_credentials.json ~/.claude/credentials/gcloud-adc.json

# Set env in settings.json so devcontainers pick it up automatically
# "env": {
#   "GOOGLE_APPLICATION_CREDENTIALS": "/home/vscode/.claude/credentials/gcloud-adc.json",
#   "GOOGLE_CLOUD_PROJECT": "<PROJECT_ID>"
# }
```

## Key Rules

- **One gcloud invocation only** — start it, keep it alive, feed it. Never restart.
- **tmux is required** — FIFO/subshell/pipe approaches fail in non-interactive environments
- **send-keys targets window name** — use `-t <window-name>` not window index for reliability
- **tee to file** — capture output to file so it can be read after the interactive prompt clears it
