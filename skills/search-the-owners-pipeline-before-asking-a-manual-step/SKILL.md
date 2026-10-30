---
name: search-the-owners-pipeline-before-asking-a-manual-step
description: Before asking the user to run commands by hand to fetch a secret/credential/config (bw get, copy into .env), search their infra repo and memories for the pipeline they already built for exactly that. Asking first wastes their time and reads as "you didn't look". Trigger - "put it in the vault", "vault에 넣으면 가져갈 수 있어?", a needed secret, a locked password manager CLI.
---

# Search the owner's pipeline before asking for a manual step

## Problem

- 증상: the agent needs a secret, finds the password-manager CLI locked, and hands the user a list of `bw unlock / bw get` commands. Two rounds of "not found" later the user says: "I built a system so you could do this — why am I doing it?"
- 근본 원인: the owner had `~/Works/_infra/scripts/secrets-sync.sh` + `secrets.manifest` (vault → 0600 leaf files the machine reads). The agent looked at the CLI state and memory index, not the infra repo. Also the pipeline only read the `password` field; the item was a secure note, so even the pipeline needed a field selector (`<item>#<field>`).
- 흔한 오해: "the vault is locked, so the human must fetch it". By design the human unlocks once — but through *their* tool, not ad-hoc commands; and the agent's job is to add the manifest line and make the tool handle the item's shape.

## Solution

1. Grep the infra/workstation repo and all project memories for the vault host, `bw `, `BW_SESSION`, `secrets` before proposing any manual step.
2. If a pipeline exists: add the manifest entry (names only, never values), extend the tool if the item shape is new (secure note fields, unlabeled values → refuse to guess, show labels only), test it with a fake CLI, then ask the user for the one human step the design requires (unlock) with a single command.
3. Do not probe keychains or other credential stores looking for an unlock secret — that is credential exploration and is blocked; the designed path is the human unlock.
4. Public values (OAuth client id) do not need the vault — ask for them directly.

## Key Insights

- A locked secret store is a designed boundary, not a dead end; the owner usually built the bridge already.
- When a tool fails with "not found", its own diagnostics should show what exists (labels/names, never values) — that turned two blind retries into one fix.
