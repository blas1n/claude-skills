---
name: outbound-connect-fail-local-vs-remote-diagnosis
description: When a host can't reach one service (e.g. github.com) but reaches others, do NOT assume a remote block / firewall / IP ban. The error TYPE discriminates: an immediate "Can't assign requested address" (EADDRNOTAVAIL) is a LOCAL socket failure (the packet never left), almost always ephemeral-port / TIME_WAIT exhaustion — not a remote block (which times out or RSTs). Check TIME_WAIT count vs the ephemeral port range first.
---

# Diagnose outbound connect failure: local stack vs remote block

## Problem

`git push` / `curl https://github.com` fails, while `curl https://google.com` works. The instinct (and the user's instinct) is "GitHub blocked our machine / IP — maybe abuse detection from all those automated requests." Hours get spent flushing DNS, checking firewalls, toggling VPNs, and waiting for a "remote block" to lift — none of which help, because the problem is local.

- Symptom: outbound to SOME hosts fails, others succeed. `curl -v` shows `Immediate connect fail for <ip>: Can't assign requested address` and fails in ~2ms.
- Root cause: **ephemeral port exhaustion**. `netstat -an | grep -c TIME_WAIT` exceeds the OS ephemeral port range (macOS: 49152–65535 = 16,384). With the pool over-subscribed, `connect()` can't allocate a local source port and fails instantly with EADDRNOTAVAIL. Whether a specific destination succeeds is probabilistic at the boundary — so it LOOKS host-specific.
- Common misunderstanding: "github fails but google works, so it's github-specific (a block/ban)." A remote block does NOT produce EADDRNOTAVAIL in 2ms — it produces a connection **timeout** or **RST** after the SYN reaches the remote. The immediate local error is the tell that the packet never left the machine.

## Solution

1. **Read the error type, not just "it failed."** `curl -v --max-time 10 https://host 2>&1 | grep -iE 'trying|connect|assign|refused|timed out'`.
   - `Can't assign requested address` (EADDRNOTAVAIL), ~ms → **local** (port exhaustion). Stop suspecting the remote.
   - `Connection timed out` / `Connection refused` (RST) after the SYN → could be remote/upstream.
2. **Count TIME_WAIT vs the ephemeral range** — the definitive test:
   ```bash
   netstat -an | grep -c TIME_WAIT          # >16k on macOS = exhausted
   sysctl net.inet.ip.portrange.first net.inet.ip.portrange.last  # the range
   ```
3. **Confirm it's not host-specific** by trying a second unrelated IP (e.g. `1.1.1.1`). If that also EADDRNOTAVAILs, it's global exhaustion, not a per-host block.
4. **Find the churn source** — what's opening thousands of short-lived sockets:
   ```bash
   netstat -an | grep TIME_WAIT | grep 127.0.0.1 | awk '{print $5}' | sed -E 's/.*\.([0-9]+)$/\1/' | sort | uniq -c | sort -rn | head
   lsof -nP -iTCP:<top-port> -sTCP:LISTEN   # who owns that port (often an SSH tunnel / proxy)
   ```
5. **Recover by draining TIME_WAIT** (these are stuck for 2×MSL):
   - **Reboot** — most reliable; clears all stuck sockets (e.g. 17,133 → 11). Outbound works immediately after.
   - Or `sudo sysctl -w net.inet.tcp.msl=1000` to drain fast, then restore `15000`. (Needs sudo — a non-interactive agent shell usually can't supply the password, so this is a user action.)
6. **DNS/route flush will NOT help** — the names resolve and routes are fine; it's the socket table, not DNS/routing.

## Key Insights

- The single most useful signal is the **error string + latency**: EADDRNOTAVAIL in milliseconds = local-stack, full stop. A remote block can't manifest that fast or that locally.
- "Some hosts work, others don't" is the *signature* of boundary-condition port exhaustion, NOT evidence of a per-host block — the opposite of the intuitive read.
- Side effect worth knowing: while ports are exhausted, containers/services that fetch over the network (e.g. `uv`/`pip` pulling deps) **crash-loop**. Don't misread that as a code/image regression — it resolves itself once the network recovers.
- Related local-tooling fallout: with the network this degraded, an SSH-based VM manager (Colima/Lima) can't set up its forwarder and either hangs 10 min or, after, fails fast with `failed to run attach disk ... in use by instance` (zombie lock) — recover with `colima stop --force` (NOT `colima delete`, which wipes the VM) then `colima start`.

## Red Flags

- "GitHub/the remote must be blocking us" — before believing it, check the error is a timeout/RST, not an immediate EADDRNOTAVAIL.
- DNS flush + route flush + VPN toggle all fail to help (because it's the socket table).
- Reachability is split across hosts and shifts run-to-run (boundary-condition allocation).
- A container that was fine starts crash-looping on dependency downloads at the same time outbound breaks.
