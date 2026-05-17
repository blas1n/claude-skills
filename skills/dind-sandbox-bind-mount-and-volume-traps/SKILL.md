---
name: dind-sandbox-bind-mount-and-volume-traps
description: Putting agent/CI execution inside a Docker-in-Docker sandbox — the bind-mount, named-volume namespace, volume ownership, and persisted-path traps that pass unit tests but break on a real DinD or a prod cutover.
---

# DinD sandbox — bind-mount, volume namespace & path traps

## Problem

When you run agent/CI execution inside a privileged `docker:dind`
sidecar (the host app spawns per-project/per-job sandbox containers
*inside* the DinD), several traps surface only on a real DinD or at
prod cutover — never in unit tests that mock the docker layer.

### Trap 1 — named-volume namespace is per-daemon

`docker run -v <named-volume>:/path` executed **against the DinD**
(`DOCKER_HOST=tcp://dind:2375 docker run -v myvol:/x ...`) creates a
volume named `myvol` **inside the DinD's own volume namespace** — NOT
the host volume `myvol`, and NOT the volume the host mounted into the
DinD container. Seeding data into "myvol" this way and expecting a
sandbox to see it → the sandbox sees an empty, different volume.

- The host volume reaches the DinD only via the *outer* mount
  (`docker run -v hostvol:/workspaces docker:dind`). Inside the DinD
  container, `/workspaces` IS that shared volume.
- To seed/inspect the shared workspace, operate on the DinD
  container's path directly: `docker exec <dind> sh -c '... /workspaces/...'`
  — never `docker run -v <name>` against the DinD.

### Trap 2 — bind-mount source resolves against the DinD's filesystem

A sandbox created with `-v /some/path:/work` has `/some/path`
resolved by the **DinD daemon against the DinD container's
filesystem**, not the host's and not the app's. If that path doesn't
exist in the DinD, Docker **auto-creates it, owned by root**. So:
- The app and the sandbox must share the workspace via a named volume
  mounted at the **same path in both** the app container and the DinD
  container — then `-v /workspaces/<id>:/work` resolves correctly.
- A path that isn't on that shared volume → the sandbox's `/work` is a
  fresh root-owned empty dir → a non-root sandbox user gets
  `Permission denied` on every write.

### Trap 3 — fresh named volume root is root-owned

A brand-new named volume's root is owned by `root:root`. A uid-1000
app can't `mkdir` project dirs in it; a uid-1000 sandbox image can't
write. Fix: a one-shot init container (runs as root, mounts the
volume) that `chown`s the volume root to the app/sandbox uid before
the app starts (`depends_on: condition: service_completed_successfully`).

### Trap 4 — persisted absolute paths survive infra migrations

A path stamped into the DB *before* a volume migration (e.g.
`project.workspace_dir = /app/data/...`) is still used *after* the
layout moves to `/workspaces/<id>`. Old rows silently point off the
shared volume → Trap 2. Cutover must clear/migrate stamped paths:
`UPDATE ... SET path_col = NULL WHERE path_col NOT LIKE '/newroot/%'`.

### Trap 5 — placeholder tokens not resolved by the new backend

If the old (host) execution path substituted a placeholder
(`<venv_python>`, `<tmpvenv>`) and the new sandbox path runs commands
literally, the placeholder reaches the shell verbatim → exit 127.
Audit every substitution the first backend did when adding a second.

## Solution

1. **One shared named volume**, mounted at the **identical path** in
   both the app and the DinD sidecar. Sandbox bind-mounts use that
   path. Never `docker run -v <name>` against the DinD to reach it.
2. **chown the volume root** to the app/sandbox uid via a root
   one-shot init service before the app starts.
3. **Match uids** — app, init, and sandbox image all uid 1000 so a
   dir created by one is writable by the others.
4. **Clear stale persisted paths** at cutover.
5. **Audit placeholder substitution** across both execution backends.
6. Build the sandbox image **into the DinD**: `docker save img |
   docker exec -i <dind> docker load` (a host build is invisible to
   the DinD; a host-reachable `DOCKER_HOST` port often isn't published
   on prod).
7. Privileged `docker:dind`, NOT rootless — rootless DinD fails on the
   Docker Desktop linuxkit kernel.

## Key Insights

- The DinD has its own image store AND its own volume namespace. "The
  volume named X" is ambiguous — host X ≠ DinD X.
- Unit tests that mock the docker layer pass through all five traps.
  Only a real-DinD e2e (or the prod cutover) surfaces them — budget
  for a live-DinD verification pass before claiming done.
- Trap 2 + Trap 3 + Trap 4 all present as the same symptom —
  `Permission denied` writing to the sandbox `/work`, or an empty
  `/work` — but have three different fixes. Check: is the path on the
  shared volume? is the volume root chowned? is a stale path stamped?

## Red Flags

- Sandbox `/work` is empty though the app "wrote" files there.
- `ls /work` shows `drwxr-xr-x root root` and the sandbox runs non-root.
- `cannot create … Permission denied` from a sandboxed file write.
- `exit 127` / "command not found" for a command that should resolve
  (placeholder not substituted, or wrong toolchain).
- A pre-existing DB row with an absolute path that predates an infra
  change.
