---
name: supabase-legacy-api-keys-migration
description: "Supabase deprecated the legacy anon/service_role JWT keys + their dashboard rotation UI. Migrate to new sb_publishable_/sb_secret_ keys. Drop-in compatible — env values change, names + apikey/Bearer header usage stay identical. Phase 1 (server) is small; Phase 2 (client) impact depends on whether frontends import @supabase/supabase-js."
version: 1.0.0
task_types: [devops, refactor]
triggers:
  - pattern: "Vercel shows `needs_attention` on the Supabase integration and the dashboard's `service_role` rotate/Roll button is gone"
  - pattern: "team wants to rotate a Supabase service-role key but the legacy rotation UI is no longer available"
---

# Supabase Legacy API Keys → New API Keys Migration

## Background

Supabase replaced the legacy JWT API keys with a new system around 2025:

| Legacy (deprecated) | New (recommended) |
|---|---|
| `anon` JWT (`eyJ...`) | `sb_publishable_<id>` |
| `service_role` JWT (`eyJ...`) | `sb_secret_<id>` |

**Key compatibility facts:**

- API contract unchanged — `apikey: <value>` header + `Authorization: Bearer <value>` still work. PostgREST, GoTrue (auth), Storage, Realtime all accept the new format transparently.
- The legacy rotation UI ("Roll" / "Regenerate") was removed. You can only **revoke** legacy keys; new keys must be **created** under the new system.
- Multiple secret keys can coexist (per-environment, per-purpose), each independently revocable. Legacy was 1 service_role per project.
- New `sb_secret_*` doesn't appear in `apikey` HTTP responses or in Vercel `needs_attention` health checks the same way — Vercel's old "Sync" button targets legacy keys; for the new system you replace env values manually.

## Migration plan (recommended ordering)

### Step 0: Inventory

Find every place that holds the legacy keys before touching anything:

```bash
# Local repos
grep -rEH "SUPABASE_SERVICE_ROLE_KEY|SUPABASE_ANON_KEY|NEXT_PUBLIC_SUPABASE_ANON_KEY|VITE_SUPABASE_ANON_KEY" \
  ~/Works/*/main/ 2>/dev/null --include="*.env*" --include="*.py" --include="*.ts" \
  | grep -v node_modules | grep -v .venv

# Vercel projects (per project, server-side)
vercel env ls

# GitHub Actions secrets
gh secret list -R <owner>/<repo>

# Live frontend bundles (catches any anon JWT inlined client-side)
for d in product1 product2; do
  curl -sL "https://$d.example.com/" \
    | grep -oE '/_next/static/chunks/[^"]+\.js|/assets/[^"]+\.js' | head -3 \
    | while read p; do
        curl -sL "https://$d.example.com$p" \
          | grep -oE 'eyJ[A-Za-z0-9_-]{20,}\.eyJ[A-Za-z0-9_-]{20,}\.' | head -1
      done
done
```

The bundle grep is the most important client-side check. If it finds an inlined JWT, that frontend uses `@supabase/supabase-js` directly and **must** be redeployed for Phase 2. If it finds nothing, the frontend is using a centralized auth layer (BFF, JWKS proxy, etc.) and only the server side needs the new key.

### Phase 1: Secret key (server-side) — small, safe

Affected: any service that needs RLS bypass — typically one (your auth/BFF backend).

1. **Supabase dashboard** → Project Settings → API Keys (separate tab from "Legacy") → "Create new secret key" → description (e.g. `<project>-prod-vercel`) → copy the `sb_secret_<id>` (shown once).
2. **Replace in Vercel env**: keep the env var name the same (`SUPABASE_SERVICE_ROLE_KEY` etc.), only swap the value to the new `sb_secret_<id>`. Code unchanged.
3. **Redeploy** the affected Vercel project. Env-only changes don't auto-redeploy unless you have that toggle on.
4. **Verify**:
   ```bash
   curl -sf -o /dev/null -w "%{http_code}\n" \
     -H "apikey: $NEW_SECRET" \
     -H "Authorization: Bearer $NEW_SECRET" \
     "$SUPABASE_URL/rest/v1/<known_table>?select=id&limit=1"
   # expect 200
   ```

### Phase 2: Publishable key (client-side) — depends on architecture

**If frontends import `@supabase/supabase-js` directly** (anon JWT inlined in bundle): each frontend must be rebuilt and redeployed. Plan time accordingly.

**If frontends use a centralized auth pattern** (no anon inline — bundle grep confirms): only the BFF / auth-app server-side env needs updating. No frontend redeploy needed.

For the centralized case (most teams should converge here):

1. Create `sb_publishable_<id>` in dashboard.
2. Update server env (`SUPABASE_ANON_KEY` and any `NEXT_PUBLIC_SUPABASE_ANON_KEY` for build-time inlining — even if dead code, keep them in sync).
3. Redeploy.
4. Verify with `curl -H "apikey: $NEW_PUB" "$SUPABASE_URL/auth/v1/health"` → 200.

### Step Final: Revoke legacy

**After Phase 1 and 2 are both deployed and verified for 24+ hours**:

1. Dashboard → API Keys → Legacy `service_role` → Revoke.
2. Same for legacy `anon`.
3. Verify: `curl -H "apikey: <OLD_JWT>" "$SUPABASE_URL/rest/v1/..."` → 401.
4. Vercel `needs_attention` flag clears automatically.

## Common traps

### Trap 1: Forgetting in-flight worktrees

Other developers' active worktrees, dev `.env` files, and personal machines may still embed the legacy `anon`. Revoke too soon → their dev environments break.

Defense: search Slack / dev wikis / `.env.example` for the legacy key fragment. Or just delay revoke until everyone's worktrees have rotated. The legacy key keeps working until you click Revoke; there's no auto-expiry.

### Trap 2: Vercel "Sync" button

For legacy keys the Supabase ↔ Vercel native integration offered a one-click Sync. The new key system doesn't use it — you set the env var manually via Vercel dashboard / `vercel env`. The `needs_attention` flag is about the *legacy* key being deprecated; clicking Sync there does nothing useful for the new system.

### Trap 3: New keys don't fall through `service_role` permission boundary expectations

`sb_secret_*` is documented as service-level (RLS-bypassing). But check your RLS policies — some explicitly look for `auth.role() = 'service_role'` or similar. With the new key system, validate each privileged code path with a real call against an RLS-protected table.

### Trap 4: GitHub Actions secrets accumulate

`SUPABASE_SERVICE_ROLE_KEY`-style secrets in GitHub Actions are easy to forget. They're not in the repo, not in Vercel, not in `.env.example`. `gh secret list` is the only catch.

### Trap 5: BFF / auth-app dead code masks impact analysis

Sometimes there's a `lib/supabase.ts` with a `createClient` call that nobody imports anymore — leftover from a refactor. Don't take its existence as evidence the frontend uses anon directly. Verify with bundle grep AND with `grep -l 'from.*lib/supabase'` for actual importers.

## Operational notes

- New keys can be tagged with a description in the dashboard (Supabase → API Keys → Description column). Use this to label which environment / which Vercel project owns each key. Cleanup after rotations becomes much easier.
- Store new keys in a password manager (Bitwarden / Vaultwarden / 1Password) **immediately** — `sb_secret_*` is shown exactly once.
- The new `sb_publishable_*` is technically safe to expose publicly (same RLS protection as legacy anon JWT), but it still identifies your project — log/redact it the same way.
