---
name: fake-test-secrets-trip-secret-scanners
description: GitGuardian (and similar PR secret scanners) flag random-looking fake secrets in tests as "Generic High Entropy Secret"; a follow-up commit does not clear the PR check because the first commit still holds it, and rewriting history may be blocked. Write fakes as low-entropy words from the start. Trigger - adding test constants for client secrets/tokens/API keys, GitGuardian check failing on a test file.
---

# Fake secrets in tests trip secret scanners

## Problem

- 증상: PR check "GitGuardian Security Checks" fails on `tests/...py` — `Generic High Entropy Secret` — for a value that was never real (`CLIENT_SECRET = "bnet-SECRET-xyz789"`).
- 근본 원인: the detector scores entropy and keyword context (`SECRET`, `TOKEN`), not reality. Mixed case + digits + a secret-ish variable name looks real.
- 흔한 오해: "push a commit that changes the value and the check goes green". It does not: the scan covers every commit in the PR, and the first one still has it. Amending + force-push removes it, but force-push may be blocked (agent permission rules, branch protection), so the only remaining fix is marking the incident as a false positive in the dashboard — a human step.

## Solution

1. From the first commit, write fakes as obvious low-entropy words: `"fake-client-secret"`, `"fake-access-token"`, `"test-api-key"`. Keep assertions that the fake never appears in logs/DB — they work the same with a word.
2. If a high-entropy fake already landed in a PR: change it in a new commit (keeps the repo clean going forward) and ask the owner to mark the GitGuardian incident as a false positive / test credential. Only rewrite history if force-push is explicitly allowed.
3. Existing repo fakes that never got flagged (e.g. older `SECRET-TOKEN-...`) are not proof that a new one will pass — detectors change and context words differ.

## Key Insights

- Choose test secrets for the scanner, not for realism: realism buys nothing in a unit test.
- A secret-scanner check is commit-scoped, not tree-scoped — "fix forward" does not clear it.
