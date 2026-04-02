---
name: devcontainer-infra-traps
description: "Devcontainer & Docker traps — dotfiles destroying worktree history, native binding mismatch, compose project name collision"
version: 1.0.0
triggers:
  - pattern: "git history lost in devcontainer, native bindings fail in container, or docker-compose projects overwriting each other"
---

# Devcontainer & Docker Infrastructure Traps

## 1. Dotfiles Destroy Worktree History

Devcontainer `--dotfiles-repository` install script may run `git init` in workspace, replacing worktree's `.git` file with a directory. All parent history lost.

**Symptoms**: `git log` shows only container commits; PRs fail with "no common history".

**Fix**: Always specify `--dotfiles-target-path`:
```bash
devcontainer up \
  --workspace-folder "$WORKSPACE" \
  --dotfiles-repository https://github.com/user/dotfiles.git \
  --dotfiles-target-path '~/.dotfiles'  # CRITICAL
```

**Verify**: `.git` should be a **file** (worktree pointer), not a directory.

**Recovery**:
```bash
git format-patch --root -o /tmp/patches/
# recreate worktree, then:
git am --3way /tmp/patches/*.patch
```

---

## 2. Native Binding Mismatch (Vite/Rolldown)

`node_modules` from macOS host → Linux container: native binaries are wrong architecture.

```
Error: Cannot find module '@rolldown/binding-linux-arm64-gnu'
```

**Fix** (inside container):
```bash
cd /workspace/frontend
rm -rf node_modules
CI=true pnpm install  # CI=true skips interactive prompts
```

**Stale Vite cache**: After code changes, `node_modules/.vite/` serves old components:
```bash
rm -rf node_modules/.vite  # Clear dep cache, restart dev server
```

**Prevention**: Add to `postStartCommand`:
```bash
cd /workspace/frontend && rm -rf node_modules/.vite
```

---

## 3. Docker Compose Project Name Collision

Multiple projects with `deploy/docker-compose.yml` all get project name `deploy`.

**Symptoms**: Deploying project B stops project A's containers.

**Fix**: Always specify project name:
```bash
docker-compose -p bsnexus -f deploy/docker-compose.yml up -d

# Or via env var
COMPOSE_PROJECT_NAME=bsnexus docker-compose -f deploy/docker-compose.yml up -d
```
