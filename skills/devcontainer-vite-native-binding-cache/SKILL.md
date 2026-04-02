---
name: devcontainer-vite-native-binding-cache
description: Vite/rolldown native bindings installed on macOS host fail inside Linux devcontainer — rm node_modules + CI=true pnpm install inside container
trigger: when Vite fails with "Cannot find module @rolldown/binding-linux-*" or ELIFECYCLE in devcontainer, or when UI shows stale content after code changes
---

# Devcontainer Vite Native Binding & Cache Issues

## Problem 1: Native Binding Mismatch

When `node_modules` is bind-mounted from macOS host into Linux devcontainer, native binaries (rolldown, esbuild, etc.) are for the wrong architecture.

```
Error: Cannot find module '@rolldown/binding-linux-arm64-gnu'
ELIFECYCLE Command failed with exit code 1
```

## Fix

```bash
# Inside the container:
cd /workspace/frontend
rm -rf node_modules
CI=true pnpm install  # CI=true skips interactive prompts
```

**NEVER** run `pnpm install` on the host and expect it to work in the container.

## Problem 2: Stale Vite Cache

`node_modules/.vite/` caches pre-bundled dependencies. After code changes (especially design system updates), the cache serves OLD components. UI looks unchanged despite code being updated.

```bash
# Clear Vite dep cache
rm -rf node_modules/.vite
# Restart dev server — it will re-bundle
```

## Problem 3: Port Already In Use

`kill -9 $(pgrep -f node)` kills the bash process itself when run inside `docker exec`. Use `-d` flag or kill specific PIDs.

```bash
# BAD — kills the bash session
docker exec container bash -c 'kill -9 $(pgrep -f node); pnpm dev'

# GOOD — separate steps
docker exec -d container bash -c 'kill specific PID'
sleep 2
docker exec container bash -c 'pnpm dev &'
```

## Prevention

Add to devcontainer `postStartCommand`:
```bash
cd /workspace/frontend && rm -rf node_modules/.vite
```
