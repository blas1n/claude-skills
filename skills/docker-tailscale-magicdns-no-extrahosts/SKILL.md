---
name: docker-tailscale-magicdns-no-extrahosts
description: Docker containers on a Tailscale-enabled host already reach tailnet hostnames + 100.x.x.x IPs — do NOT propose docker-compose extra_hosts patches before testing.
version: 1.0.0
task_types: [devops, debugging]
category: trap
---

# Docker → Host service via Tailscale (no extra_hosts needed)

## Wrong instinct

When a container needs to reach a service running on the host
(ollama at :11434, a self-hosted Postgres, Caddy, …), the textbook
suggestion is one of:

- Add `extra_hosts: ["host.docker.internal:host-gateway"]` to the
  docker-compose service
- Patch the app to use `host.docker.internal:<port>`
- Bind the host service to `0.0.0.0` instead of `127.0.0.1`
- Use `network_mode: host`

**Test first. On any machine that runs Tailscale, these patches are
typically unnecessary.** Containers inherit the host's resolv.conf,
which already points at the Tailscale resolver (100.100.100.100 on
macOS / Linux), so tailnet hostnames + 100.x.x.x IPs resolve from
inside the container without any docker-compose changes.

## What actually works

On a Mac Mini ("bsserver") with Tailscale + Lima-VM ollama bound to
the VM's `127.0.0.1:11434` (which Lima publishes on the host):

```bash
docker exec <container> python3 -c "
import urllib.request
for url in ['http://bsserver:11434/api/tags',
            'http://100.96.108.30:11434/api/tags',
            'http://host.docker.internal:11434/api/tags']:
    print(url, '->', urllib.request.urlopen(url, timeout=3).status)
"
# bsserver:11434           -> 200    ← tailscale magicDNS
# 100.96.108.30:11434      -> 200    ← tailscale tailnet IP
# host.docker.internal:11434 -> 200  ← docker host gateway (also works)
```

All three return 200 from inside an unmodified container — no
`extra_hosts`, no `network_mode: host`, no Dockerfile change.

The cleanest of the three is the magicDNS hostname (`bsserver`) —
it's stable across IP changes and self-documenting.

## Why it works

1. Docker copies the host's `/etc/resolv.conf` into the container at
   start (default Docker daemon behavior on Mac/Linux, unless
   `--dns` overridden).
2. macOS with Tailscale installs the Tailscale userspace resolver in
   the host's DNS chain, so `bsserver`, `bsmain`, etc. resolve to
   100.x.x.x addresses.
3. The container's request to `bsserver:11434` resolves to the host's
   tailnet IP and routes via Docker's bridge → host's tailnet
   interface → loopback to the actual listener (Lima's port forward
   from VM → host loopback handles the bind-on-127.0.0.1 case
   transparently when the source is the host itself).

## Diagnostic recipe

Before proposing infra patches, run this one-liner from inside the
container:

```bash
docker exec <container> python3 -c \
  "import urllib.request, sys; \
   url=sys.argv[1]; \
   r=urllib.request.urlopen(url, timeout=3); \
   print(url, r.status)" \
  "http://<hostname-or-ip>:<port>/<healthcheck-path>"
```

If it returns 200 → no infra change needed; the consumer config
(executor base_url, db connection string, …) is the only place to
touch.

If it fails → only then consider:
- Tailscale not installed / not in resolv.conf chain → `extra_hosts`
- Container uses custom DNS overriding host's → `dns:` block in
  docker-compose
- Service genuinely bound to a docker-internal interface only

## Specific gotcha — Lima ollama on macOS

On macOS, `lsof -nP -iTCP:11434` shows `ollama 583 blasin TCP
127.0.0.1:11434 (LISTEN)` — looks loopback-only. **It still works
from containers** because Lima's port-forward layer accepts the
connection on the host's tailnet IP and forwards into the VM. Don't
treat the lsof bind address as authoritative for "is this reachable
from a container" — test from the container.

## When this saves time

The wrong path (proposing docker-compose `extra_hosts` + rebuild +
redeploy) is hours. The right path (test → realize it already works
→ change one config field) is minutes. Even when you're sure
`extra_hosts` is needed, run the diagnostic first.
