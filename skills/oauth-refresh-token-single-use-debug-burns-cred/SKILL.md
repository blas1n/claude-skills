---
name: oauth-refresh-token-single-use-debug-burns-cred
description: OAuth refresh tokens (GitHub, Notion, Slack, …) are SINGLE-USE — calling `provider.refresh(refresh_token)` from a debug REPL or one-shot script without persisting the returned new tokens to DB silently invalidates the credential. The new tokens vanish at process exit, the OLD refresh in DB is now rejected by the provider, every subsequent dispatch fails with `bad_refresh_token` / 401. Only a fresh OAuth flow recovers. Treat refresh as a database-side transaction, not a function call.
---

# OAuth refresh token single-use trap — debug scripts kill the credential

## Symptom

Production dispatch fails:

```
remote: Invalid username or token. Password authentication is not supported
fatal: Authentication failed for 'https://github.com/...'
```

OR

```
github token exchange failed: bad_refresh_token
(The refresh token passed is incorrect or expired.)
```

DB shows the OAuth row is still bound; `connector_oauth_tokens` has `access_token` + `refresh_token` ciphertext present, `expires_at` in the past. Looks fine.

## The trap

OAuth refresh tokens are **single-use by design** (GitHub Apps, Notion, Slack, modern Auth0 setups). When you call:

```python
new = await provider.refresh(refresh_token=old)
# new.access_token + new.refresh_token both fresh
# but old.refresh_token is NOW INVALIDATED on the provider side
```

If you DON'T persist `new` to DB right away, the old refresh in DB is dead and the new ones are gone at process exit. The DB row is now a credential ghost — looks alive, the provider rejects it.

## When this bites

This bites debug iterations. A typical sequence:

1. Production dispatch is failing. You suspect refresh isn't running. You write a one-shot script:

   ```python
   provider = get_provider("github")
   refresh_token = cipher.decrypt(token_row.refresh_token_ciphertext)
   refreshed = await provider.refresh(refresh_token=refresh_token)
   print("REFRESH SUCCEEDED, new access_token:", refreshed.access_token[:8])
   ```

2. The script prints "REFRESH SUCCEEDED" — you confirm refresh works in isolation. But you didn't call `upsert_token(...)` + `session.commit()`.

3. Process exits. The new tokens are gone. The provider has already invalidated the old refresh.

4. Production dispatch retries → reads the OLD refresh from DB → provider returns `bad_refresh_token`. Now it's permanently dead.

5. You debug for another hour wondering why refresh "stopped working" — it didn't; you killed the credential.

## Why it's silent

The refresh endpoint returns 200 + new tokens. The OLD refresh's invalidation is server-side and asynchronous-to-you. The provider doesn't say "I am invalidating the one you just sent." Your "REFRESH SUCCEEDED" print is true. The persistence is what you missed.

## Detection

Before writing ANY OAuth debug script that calls `provider.refresh`, ask:

- Will the new tokens be persisted to the same DB row the next production call reads?
- If not, am I OK with killing this credential?

The answer in production-debug is almost always: NO and NO.

## Recovery

There is no in-band recovery. The provider-side state is gone. You must:

1. Founder/user runs the OAuth flow again (Connect with X).
2. New tokens are persisted by the OAuth callback path.
3. Production retries with the fresh refresh.

If the OAuth flow is gated behind a UI that doesn't surface the dead-credential state (e.g. shows "Connected" because `is_active=true`), the user has no path forward without a separate fix — see the companion lift to surface needs_reauth on the row.

## Safe-debug patterns

If you MUST exercise refresh from a script:

1. **Persist the new tokens**:
   ```python
   async with sf() as s:
       await load_app_credential_providers(s, cipher)  # production-equivalent bootstrap
       provider = get_provider("github")
       refresh = cipher.decrypt(row.refresh_token_ciphertext)
       refreshed = await provider.refresh(refresh_token=refresh)
       await upsert_token(
           s, connector_account_id=row.connector_account_id,
           provider="github", token=refreshed, cipher=cipher,
       )
       await s.commit()
   ```

2. **Go through `resolve_connector_credentials`**, not `provider.refresh` directly — it includes the persist + commit path.

3. **Use a sacrificial OAuth account in a test workspace** (one you don't mind reconnecting) when iterating on provider code.

## Pattern beyond OAuth

This is a special case of the general "API call has side effects on remote state I didn't persist locally" pattern. Anything that returns a new token / cursor / sequence number from a remote — and the remote invalidates the old one — must be persisted in the same transaction as the call. Examples:

- AWS STS AssumeRole + temporary credentials
- Long-poll cursors / Stripe pagination tokens
- Webhook signing key rotations

The "fire a debug script to test it" instinct is the trap. Always test through the same code path production uses.

## Origin

BSVibe E45 dogfood (run 5a695eb8, 2026-06-17). A standalone `dispatch_one.py` debug script was used to retry a stuck deliverable. The script imported `build_delivery_adapter` directly but didn't `register_configured_providers` / `load_app_credential_providers`, so the provider registry was empty and `resolve_connector_credentials` silently no-op'd refresh. To verify refresh was reachable, a separate `refresh_test.py` ran `provider.refresh()` directly — succeeded, printed the new tokens, exited. The next dispatch attempt found `bad_refresh_token` in DB and the credential was unrecoverable without re-OAuth.

Lift E45 added typed `ConnectorReauthRequired` so future failures surface clearly; lift E46 added a `needs_reauth` row status + PWA Reconnect CTA so the user sees the dead state instead of a stale "Connected" badge.
