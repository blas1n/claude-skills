---
name: slim-base-image-missing-shellout-tools
description: Minimal base images (python:slim, debian:slim, alpine, distroless) omit common CLI tools like git, ssh, rsync. Python code that subprocess-calls them passes all unit tests on dev hosts and fails only at runtime in the prod container.
---

# slim base image missing shellout tools

## Problem

Python (or any) code that shells out to a binary via subprocess will work on every developer machine and CI runner — because those hosts have a full OS install — and then fail on a slim/alpine/distroless production image that omits the binary.

Concrete cases:
- `python:3.11-slim` — no `git`, no `ssh`, no `rsync`, no build tools.
- `python:3.11-alpine` — uses musl, missing the same tools *and* glibc-linked wheels often break.
- `gcr.io/distroless/python3` — no shell at all; subprocess to anything will fail.
- `debian:bookworm-slim` — same as the python slim variants.

Symptom: container starts cleanly, app boots, the moment a code path that calls the missing tool runs you get `exec: "git": executable file not found in $PATH` (or equivalent). Unit tests have nothing to say because they imported the module fine and the host had `git` on PATH.

## Solution

**Treat subprocess dependencies as first-class build inputs**, declared in the Dockerfile alongside Python deps:

```dockerfile
FROM python:3.11-slim AS base

# W1/W2 — git is required for the product workspace + per-run worktree
# lifecycle (backend.storage.product_workspace shells out to git via
# subprocess). The slim base doesn't ship it.
RUN apt-get update \
    && apt-get install --no-install-recommends -y git \
    && rm -rf /var/lib/apt/lists/*
```

Put the install **early** (before deps + source copy) so it's a stable cache layer and rebuilds are fast.

For multiple tools, batch into one `RUN` to keep layers tight:

```dockerfile
RUN apt-get update \
    && apt-get install --no-install-recommends -y git openssh-client rsync \
    && rm -rf /var/lib/apt/lists/*
```

**Comment the *why*.** Future readers see `RUN apt-get install git` and wonder if it's safe to remove — a one-line comment naming the calling module ends that conversation. The comment should reference the *code path* that needs it, not just "needed for X feature."

## Key Insights

- **Unit tests cannot catch this class of bug.** A `which git` check at import time would, but nobody writes those. The only honest defense is: every time you add a `subprocess.run([...])` or `create_subprocess_exec(...)` for a non-Python binary, ask "is this binary in the prod image?" and either add it to the Dockerfile or document why it's already there.
- **`--no-install-recommends` is the right default for slim images.** Without it, `apt-get install git` pulls in `git-man`, `liberror-perl`, `perl`, etc. — easily 50MB of recommends you don't need.
- **Distroless = no subprocess.** If you're on a distroless base and need to shell out, you either (a) move to a non-distroless base, or (b) reimplement the call in-process (e.g. `pygit2` instead of `git`). Don't try to bolt a binary onto distroless.
- **The hotfix is one line — but the *finding* requires production traffic.** This is one of the strongest arguments for a smoke test that actually exercises the shellout path against the built image, not just against `pytest` on the host.

## Red Flags

- New code adds `subprocess.run([...])` / `create_subprocess_exec(...)` calling a non-Python binary.
- Dockerfile starts with `FROM python:*-slim` or any `-slim`/`-alpine`/`distroless` variant.
- Code review focuses on the Python logic; nobody asks "is X on the image?"
- CI is green, dev container is green, prod logs show `executable file not found in $PATH`.
- A Dockerfile has no `RUN apt-get install ...` line at all *and* the app shells out to a CLI tool.

## Verification recipe

When you add a subprocess call to a non-Python tool, run this against the built prod image once:

```bash
docker build -t app:check -f deploy/Dockerfile.backend .
docker run --rm app:check sh -c 'command -v <tool> || echo MISSING'
# expected: prints the path; if MISSING, add it to the Dockerfile
```

A single line in your release checklist. Saves a hotfix.

## When this fired

BSVibe W2 dogfood (2026-05-27): `backend.storage.product_workspace` shells out to `git` to init the product repo and manage per-run worktrees. All 2605 unit tests green on host (which has git). Prod container (`python:3.11-slim`-based) produced empty product workspaces with `exec: "git": executable file not found in $PATH` in the backend logs. PR #173 added `apt-get install -y git` to `deploy/Dockerfile.backend` — a 4-line hotfix that should have been part of the W1 PR.
