---
name: vercel-cli-root-directory-collision
description: Vercel CLI `vercel --prod --force` fails with "frontend/frontend" path lookup when `.vercel/project.json` lives inside a subdirectory AND the server-side rootDirectory ALSO points to that subdirectory. Use REST API `/v13/deployments` to bypass.
---

# Vercel CLI cwd × rootDirectory Collision

## Problem

Running `vercel --prod --force --yes` from a frontend subdirectory of a monorepo fails with misleading errors like:

```
Error: The provided path "~/Works/<repo>/main/frontend/frontend" does not exist.
Error: No fastapi entrypoint found. Add an 'app' script in pyproject.toml or define an entrypoint in one of: app.py, ...
```

- **Symptom**: Vercel CLI tries to deploy from a path that has the subdirectory name **twice** (`frontend/frontend`), or detects the wrong framework after walking up to repo root.
- **Root cause**: Vercel CLI treats the directory containing `.vercel/project.json` as the project root and uploads it as the source. The server then applies its **own** `rootDirectory` setting on top of what was uploaded. If `.vercel/` is at `<repo>/frontend/.vercel/` AND server-side `rootDirectory: "frontend"`, the server resolves the build root to `frontend/frontend` — which doesn't exist.
- **Common misdiagnosis**: "framework auto-detect bug" or "wrong working directory". Moving `.vercel/` to repo root makes it worse (server still appends `frontend`, now the upload doesn't have a `frontend/` subdirectory at all).

## Solution

**Bypass the CLI entirely**. The Vercel REST API `POST /v13/deployments` triggers a fresh git-based build that respects server-side `rootDirectory` correctly:

```bash
TOKEN=$(jq -r '.token' "$HOME/Library/Application Support/com.vercel.cli/auth.json")
TEAM=team_xxxxxxxxxxxx                    # your team id
PROJECT_NAME=<project-name>                # e.g. bsage-app
REPO_ID=<github-repo-numeric-id>          # from `vercel project ls` or /v9/projects/<id>

curl -sf -X POST \
  "https://api.vercel.com/v13/deployments?teamId=${TEAM}&forceNew=1&skipAutoDetectionConfirmation=1" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "'"$PROJECT_NAME"'",
    "gitSource": {"type": "github", "ref": "main", "repoId": '"$REPO_ID"'},
    "target": "production"
  }' | jq '{id, url, readyState}'
```

Verify completion:

```bash
DPL_ID=dpl_xxxxxxxx
curl -sf "https://api.vercel.com/v13/deployments/${DPL_ID}?teamId=${TEAM}" \
  -H "Authorization: Bearer $TOKEN" | jq '{readyState, errorMessage, ready}'
# expected: readyState: "READY"
```

To find `repoId`:

```bash
curl -sf "https://api.vercel.com/v9/projects/<projectId>?teamId=${TEAM}" \
  -H "Authorization: Bearer $TOKEN" | jq '{rootDirectory, gitRepository}'
```

## Key Insights

- **Server-side `rootDirectory` is independent of CLI cwd.** They compose, not override. The CLI does not consult the project settings to subtract `rootDirectory` from its upload path.
- **`vercel --force` busts the build cache but not the path collision.** If you're force-deploying because env vars need re-baking, the same collision recurs every retry.
- **Removing `.vercel/` and re-linking does not help.** New CLI runs ask which project to link, but the collision is server-side; even a fresh link reproduces the issue.
- **REST API trigger is the only reliable path** for monorepo Vercel projects with non-root `rootDirectory`. It uploads nothing — it tells Vercel "rebuild from git ref X", which is exactly what GitHub-push triggered builds do.

## Red Flags

Suspect this trap when you see:

- `frontend/frontend` (or any doubled-segment path) in the CLI error
- Vercel CLI auto-detects a backend framework (FastAPI, Express) when you're trying to deploy a frontend
- The Vercel project settings show `rootDirectory: "frontend"` (or any non-null value) and you're running CLI from inside that subdirectory
- `vercel --prod --force` was working when triggered from GitHub push but fails from CLI — the GitHub trigger doesn't upload anything, while CLI does

## Context

Discovered 2026-05-03 while force-rebuilding 4 Vercel frontends (BSage, BSupervisor, BSNexus, BSGateway) after env var changes. All four had `rootDirectory: "frontend"` configured. Plan documented the wrong recovery path (CLI), and the right fix was the REST API trigger. Saves ~10–15 minutes of confused retries per affected project.
