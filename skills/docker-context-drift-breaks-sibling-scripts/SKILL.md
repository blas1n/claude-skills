---
name: docker-context-drift-breaks-sibling-scripts
description: The docker CLI's current context is GLOBAL mutable user state. A `colima start <other-profile>` anywhere repoints every unpinned `docker` call on the host at a VM with none of your containers — so monitors page "container down" while production is healthy, and backups abort with "postgres is not running". Pin DOCKER_CONTEXT in every script, not just the one that already broke.
category: trap
---

# Docker context drift silently breaks every unpinned script on the host

## Problem

`docker context use` / `colima start <profile>` writes to `~/.docker/config.json`
— **global, per-user, persistent**. Every `docker` invocation on the host that
does not pin a context follows it, including scripts written months apart by
people who never touched the other profile.

The failure does not look like a context problem:

| Script | What it reports | What is true |
|---|---|---|
| watchdog | postgres container down | postgres `Up 5 days (healthy)` |
| backup | `FAILURE — postgres container is not running` | it is running; **the day's backup never happened** |
| deploy | `Done` | built and started a duplicate empty stack in the wrong VM |

`docker inspect <name>` against the wrong daemon does not error — it returns
*nothing*, which every one of these scripts reads as "absent implies down".

### Two things make this expensive

**1. The noise buries a real failure.** The watchdog above fired three false
lines every two minutes. Underneath them sat a true one — "DB backup not
refreshed in 27h" — caused by the *same* drift. Nobody reads the fourth line of
an alert that has cried wolf for hours. A monitor that cries wolf is worse than
no monitor, because the next real outage reads like more noise.

**2. Hardening one script does not harden its siblings.** Here `autodeploy.sh`
already carried the fix *and a detailed incident comment* about a previous
occurrence — while `watchdog.sh` and `backup.sh`, in the same directory, same
host, same hazard, did not. The knowledge existed and stayed local to one file.

## Solution

### Pin the context in every script that names a container

```bash
export DOCKER_CONTEXT=colima     # or: docker --context colima ...
```

Put it next to the `export PATH=` line every launchd/cron script already has,
with a comment saying what breaks without it. `DOCKER_CONTEXT` beats
`--context` on each call: one line, and it covers `docker compose` too.

### Sweep the whole directory, not the file that failed

```bash
cd /path/to/scripts && for f in *.sh; do
  grep -q "docker" "$f" || continue
  grep -q "DOCKER_CONTEXT" "$f" && echo "OK   $f" || echo "RISK $f"
done
```

Then triage by blast radius — which of them actually name production
containers:

```bash
grep -o "myapp-prod-[a-z-]*" *.sh | sort -u
```

### Diagnose in seconds

When a monitor says a container is down, check the context before checking the
container:

```bash
docker context ls          # the '*' may not be where you think
docker --context <right> ps --format '{{.Names}}\t{{.Status}}'
```

If `docker ps` shows an unfamiliar (or empty) set of containers, stop debugging
the service.

### After fixing the noise, re-read the alert

Clearing false positives is not the end of the incident — it is what makes the
remaining line legible. Run the monitor once by hand and treat whatever survives
as new information:

```bash
bash watchdog.sh && cat ~/.state/watchdog.state   # empty == genuinely all clear
```

Here that step is what surfaced the missed backup, hours after it was skipped.

## Related

- `manual-deploy-races-the-autodeploy-poller`
- `absence-measurement-validity-check` — "nothing found" needs the producer verified first
- `bsvibe-deploy-traps-container-name-and-dirty-tree`
