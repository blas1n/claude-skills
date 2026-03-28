---
name: docker-compose-project-name-trap
description: "Multiple projects with deploy/docker-compose.yml share project name 'deploy' — always use -p flag or COMPOSE_PROJECT_NAME"
---

# Docker Compose Project Name Trap

## Trigger
When multiple projects each have `deploy/docker-compose.yml` and are deployed from the same machine.

## Problem
`docker-compose -f path/to/deploy/docker-compose.yml up -d` uses the **parent directory name** as the project name. If all projects put their compose file in `deploy/`, they all get project name `deploy`, causing:

- Containers from different projects overwrite each other
- `docker-compose ps` shows containers from all projects mixed together
- `docker-compose down` kills containers from other projects

**Symptoms:**
- Deploying project B stops project A's containers
- `docker ps` shows only one project's containers despite deploying multiple

## Solution

**Always specify project name explicitly:**

```bash
# Manual deploy
docker-compose -p bsnexus -f ~/Works/BSNexus/main/deploy/docker-compose.yml up -d

# In autodeploy scripts
PROJECT_NAME=$(echo "$name" | tr '[:upper:]' '[:lower:]')
docker-compose -p "$PROJECT_NAME" -f "$COMPOSE" up -d --build
```

Or set via environment variable:
```bash
COMPOSE_PROJECT_NAME=bsnexus docker-compose -f deploy/docker-compose.yml up -d
```

## Why
Docker Compose derives the default project name from the directory containing the first `-f` file. With a shared `deploy/` convention, this is always `deploy`. The `-p` flag overrides this.
