---
name: status-code-is-not-a-reason-code
description: "An endpoint that refused for exactly one reason gets a client that keys its message off the HTTP status. Add a second refusal reason and that mapping shows the WRONG actionable hint — plausible, silent, and reported by nobody. Before adding a refusal, open the existing client mapping; ship the reason as a code in the body, and take any number in the copy from the response."
version: 1.0.0
category: trap
---

# The status code stops being an identifier at the second refusal reason

## When to use

You are about to make an existing endpoint refuse for a **new** reason —
a quota, a plan limit, a feature flag, a state precondition — on a surface
that already refuses for something else.

Trigger words: "also reject when…", "add a 400 for…", "cap this",
"gate this behind the plan", "return 409 if…".

## Problem

While an endpoint had exactly one refusal cause, keying on the status was
correct, and it reads as correct forever:

```tsx
// 400 here can only mean "this workspace has no products"
setError(err.status === 400 ? t("errorNoProduct") : t("errorSend"));
```

Add a second cause with the same status and the branch answers confidently and
**wrongly**: a founder with a dozen products is told to create one.

What makes this worse than an ordinary bug:

* **No error, no red, no log.** The user sees a fluent, localized, plausible
  sentence. It is simply about the wrong thing.
* **The new code looks fine.** The defect is in a file the PR never opens —
  a client written months earlier under an assumption the PR just invalidated.
* **Tests stay green.** The old mapping's test still passes (its cause still
  maps correctly); the new refusal's test asserts the status, which is right.
  Nothing asserts *which sentence a user sees for the new cause*.

## Recognizing it

Grep the client for branches on a bare status before adding the refusal:

```bash
rg "status === (400|403|409|422)" --type ts
rg "\.status_code == (400|403|409)"   # server-side callers too
```

Any hit whose comment or copy names **one specific cause** is a landmine the
moment a second cause shares that status.

## The fix

1. **Open the existing mapping in the same PR.** This is the whole discipline.
   The grep above takes seconds; skipping it is how the defect ships.
2. **Send a reason code, not just a status.** FastAPI's `detail` accepts an
   object:

   ```python
   raise HTTPException(
       status_code=status.HTTP_429_TOO_MANY_REQUESTS,
       detail={"code": "run_cap_reached", "limit": limit, "held": held},
   )
   ```

   The client branches on `err.reason?.code`, never on the number alone.
3. **Pick a status that is not already spoken for**, as a second line of
   defence — 429 for a quota, 402 for a plan wall. But do not *rely* on it:
   the next reason will collide with something.
4. **Any number in the copy comes from the response.** A hard-coded "3" lies
   for every tenant on a different limit. Pin it:

   ```tsx
   it("takes the number from the response, not a hardcoded free-plan 3", ...)
   // respond limit: 10 → the sentence must say 10
   ```
5. **Do not render the backend's `detail` string verbatim** on a localized
   surface — that is how English lands on a Korean screen. The server sends the
   code and the numbers; the client owns the sentence.
6. **Keep a control test for the OLD refusal.** Without it, deleting the
   original branch leaves every new test green.

## Verification

Cut each wire separately and watch only its own tests go red:

| cut | expect red | expect still green |
|---|---|---|
| remove the new reason branch in the client | new-reason tests | the old-cause control |
| unwire the refusal on surface A (REST) | A's tests | surface B's tests |
| unwire the refusal on surface B (MCP/CLI) | B's tests | A's tests |

If one cut reddens both surfaces, they share a guard and one of them is not
actually wired — the classic mirrored-surface drift.

## Measured case (BSVibe, 2026-09-03)

`POST /api/v1/messages` had refused only for a zero-product workspace (400).
Adding a free-plan concurrent-run cap as another 400 would have shown
*"Create a product first"* to founders with products. Shipped instead as
429 + `{code, limit, held}`, with the client branching on `code` and the
limit interpolated from the response.

## Related

* `single-active-resolver-degrades-on-new-account-class` — same shape one layer
  down: a discriminator that was unique stops being unique when you add a
  second class of the thing.
* `mirrored-surface-drifts-in-the-direction-of-least-testing` — share the RULE,
  keep the error faces separate, test both.
