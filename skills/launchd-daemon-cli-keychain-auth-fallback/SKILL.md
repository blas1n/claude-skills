---
name: launchd-daemon-cli-keychain-auth-fallback
description: A CLI tool (claude/gh/aws/codex…) invoked by a launchd/systemd daemon fails auth with 401 while the identical command works in your interactive shell — because the daemon's security session can't read the OS keychain and silently falls back to a stale on-disk credential. Diagnose from the daemon context, not your shell.
---

# Daemon-invoked CLI 401 — keychain unreachable → stale on-disk credential fallback

## Problem

A long-running background daemon (macOS launchd LaunchAgent, Linux systemd
service) spawns a CLI tool as a subprocess (e.g. `claude --print`, `gh`, `aws`,
`codex`). The CLI fails authentication — `Failed to authenticate. API Error: 401`
/ `Invalid bearer token` — and the daemon's job exits non-zero. The SAME command,
with the SAME flags and env, run by hand in your terminal, succeeds.

- **증상**: daemon job → CLI exits 1 with a 401/auth error, every time; your
  interactive run of the byte-identical command succeeds. Token file on disk
  looks valid (future `expiresAt`), so "expired token" is ruled out.
- **근본 원인**: on macOS the CLI stores its live credential in the **Keychain**
  (`security` item, e.g. `"Claude Code-credentials"`), and the Keychain item's
  ACL grants only the CLI binary. A **launchd/GUI-agent security session cannot
  unlock/read the login Keychain** the way an interactive Terminal session can,
  so the CLI silently **falls back to the on-disk credential file**
  (`~/.claude/.credentials.json`) — whose token was server-rotated stale long ago
  → 401. (Linux analog: a service unit without access to the user keyring /
  `$XDG_RUNTIME_DIR`/dbus session falls back to a stale `~/.config/...` file.)
- **흔한 오해**: the 401-after-retries pattern reads like **rate limiting /
  quota / "too much concurrent load"**. It is NOT — a 401 is auth, not 429, and
  it's deterministic by *execution context*, not by load. Whole debugging rounds
  get burned chasing RPM/TPM throttle when the discriminator is daemon-vs-shell.

## Solution

1. **Reproduce from the DAEMON context, not your shell.** Your interactive
   reproduction is contaminated — it inherits your session's keychain access (and
   possibly auth env vars). Prove the failure where it actually runs:
   - Prepend a logging shim dir to the daemon's `PATH` (edit the plist/unit env),
     reload the daemon, and have the shim log argv/env/stdin and run ONE trivial
     control call (`echo hi | claude --print --model haiku`) before exec-ing the
     real binary. If the trivial control 401s too → it's the context, not the
     prompt/flags/rate.
2. **Confirm the keychain split.** `security find-generic-password -s "<svc>"`
   shows the item EXISTS; `-w` returns empty (ACL bound to the binary). The
   on-disk credential file token, tested raw against the API, is rejected
   (rotated) while the interactive CLI's keychain token works.
3. **Fix by injecting the credential via an env var the daemon passes through.**
   Generate a long-lived token (`claude setup-token`, a service PAT, an API key)
   and set it in the daemon's `EnvironmentVariables`. **Mind the env sanitizer**:
   a worker that strips `CLAUDE_CODE_*` from the subprocess env will drop
   `CLAUDE_CODE_OAUTH_TOKEN` — use a var it preserves (`ANTHROPIC_AUTH_TOKEN`
   sends the OAuth token as the bearer and overrides keychain).
4. Reload the daemon (`launchctl bootout`/`bootstrap`, not just `kickstart -k`,
   to re-read plist env) and re-verify from the daemon context.

### Durable fix (don't pin a static token)

A static token in the plist expires in hours. For a stable daemon, make it
**self-manage the OAuth lifecycle**: keep its OWN credential file (separate from
the CLI's, so an interactive re-login can't clobber it), refresh the access
token when it nears expiry, and inject the fresh token via the passed-through env
var per invocation. Key points proven in production:

- Refresh tokens are **single-use** — persist the rotated pair atomically and
  serialise refresh across processes with an `flock` (else a concurrent refresher
  gets `invalid_grant`).
- Refresh only when within a buffer of expiry (cheap per-call check; network only
  every ~token-lifetime). Soft-fail to None so the CLI's own auth is the fallback.
- Force-verify the refresh path live (temporarily set `expires_at` near now) —
  don't wait to discover at real expiry that the refresh endpoint/UA is blocked
  from the daemon's network context.

```bash
# launchd reload that actually re-reads EnvironmentVariables:
launchctl bootout gui/$(id -u)/com.x.worker
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.x.worker.plist
```

## Key Insights

- A token's local `expiresAt` being in the future does NOT mean it's valid — the
  server can rotate/revoke it (a refresh elsewhere rotated the family). "Not
  expired by clock" ≠ "accepted".
- The keychain is the live store; the on-disk file is a **stale mirror** the CLI
  uses only as fallback. Refreshing the *file* token (even successfully, via the
  OAuth endpoint) does NOT help if the CLI still prefers the unreachable keychain.
- `env -i HOME=… PATH=… <cli>` from your shell is NOT a faithful daemon repro —
  keychain access is a property of the **security session**, not the env. Only a
  control call spawned by the daemon itself is decisive.
- `kickstart -k` restarts the process but does NOT reload plist `EnvironmentVariables`; you need bootout+bootstrap (or unload/load).

## Red Flags

- "Works when I run it, fails from the cron/launchd/systemd job" + a 401/auth
  error (not 429/connection).
- The failure is deterministic per-context and clears the moment you run it in
  Terminal — yet you keep theorizing about rate limits / load / concurrency.
- An OS keychain item for the tool exists but `security … -w` (or `secret-tool`)
  returns nothing, and an on-disk credential file is present.
- A worker/orchestrator sanitizes the subprocess env by prefix
  (`CLAUDE_CODE_*`, `AWS_*`…) — it may be stripping the very token var you need;
  pick a passed-through var.
