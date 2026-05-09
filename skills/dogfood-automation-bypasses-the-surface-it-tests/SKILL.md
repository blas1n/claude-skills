# Dogfood automation must preserve the user-facing surface, not bypass it

## When this applies

You're preparing a dogfood / hands-on validation session and reach for automation:

- "Issue a PAT for the agent" → write a script that calls `/api/tokens` directly with a service-role token
- "Spin up the test data" → write a SQL seed
- "Login as the test user" → set the cookie / inject the JWT manually
- "Open the dashboard" → bypass with a direct REST call to the same data

The script works, the agent has a token, the dogfood "starts" — but the **surface you were supposed to be dogfooding never executed**. If the login page is broken, the dashboard is confusing, the form has bad validation, the copy-button is missing — your automation never touched any of it.

This is a category mistake: dogfood is "use the product like a real user does" → automating the user's path defeats the purpose. The most-friction path is exactly what you wanted to test.

## How to spot it before shipping the handoff

When drafting a dogfood plan, for each automation step, ask:

1. **Is this step a UI / CLI / human-facing surface in production?**
2. **If yes — is my automation skipping it or driving it?**

"Skipping" means using an API or DB the user wouldn't touch (e.g. POST `/api/tokens` directly). "Driving" means scripting the same path the user would walk (e.g. Playwright clicking the "Issue token" button).

For dogfood, **prefer manual or driving over skipping**, even when skipping is 10× faster. The ROI on dogfood is the bug-list it produces, not the tasks it completes.

## Defenses

**Default order**:

1. **Human walks the path** — primary. Document friction in real time. This is the irreducible baseline.
2. **Driving automation** (Playwright clicking, CLI device-flow) — secondary. For repeat runs / CI. Still touches the surface.
3. **Skipping automation** (REST bypass, DB seed) — fallback only. Justify in writing why.

When the fallback fires, **that's a finding** — log "had to bypass because X" as a high-priority gap.

**Handoff documents**: write the manual path first, then list any automation as "fallback only when [specific condition]".

## Why agents (and tired humans) default wrong

Automation is the muscle reflex when an agent reads "set up dogfood". It's reliable, scriptable, idempotent — all virtues for normal work. The trap is that those virtues are *anti-virtues* for dogfood: dogfood wants the brittleness, the slow first-time experience, the friction.

When the user says "do dogfood for X", the right opening question is "what's the user-facing path I should walk?" — not "what's the API I can call?".

## Concrete instance

**2026-05-09** — BSVibe Phase 8 production dogfood handoff prep.

- v1 of the plan: I wrote `~/Works/_e2e/scripts/issue-prod-pat.sh` — Supabase password-grant + REST POST `/api/tokens`. The script worked first try, output a valid PAT. Felt productive.
- User: *"pat 발급도 자동 되지 않아?"* → I confirmed yes, integrated script into handoff as primary path.
- User (second redirect): *"pat 발급을 api 기반이 아니라 웹 로그인 기반으로 해보는게 더 도그 푸딩 아닐까"* → realized I'd automated past the surface I was supposed to validate. Restructured handoff: dashboard browser-flow as Task 0 (primary), the script demoted to fallback-only with a "log why if used" gate.
- User (third redirect): *"cli의 login 명령어 사용하는거지?"* → checked, found 4 product CLIs don't expose `login`/`profile` despite `bsvibe-cli-base/device_flow.py` having the infrastructure. **The dogfood prep itself surfaced a real pre-existing CLI gap** before any dogfood task ran. Logged as pre-discovered finding #2 in the handoff.

The lesson: I should have started by asking "what surfaces does dogfood need to walk?" — would have caught the CLI login gap on day one instead of after two redirects + a wasted automation script.
