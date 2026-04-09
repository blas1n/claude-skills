# Supabase OAuth Redirect Trap

## When to Apply

- Using Supabase Auth with OAuth providers (Google, GitHub, etc.)
- The app has a custom auth server (not Supabase's built-in hosted UI)
- OAuth flow uses `redirect_to` parameter on `/auth/v1/authorize`

## The Trap

Supabase's `/auth/v1/authorize` accepts a `redirect_to` parameter to control where the user goes after OAuth. But this URL is **silently validated** against `uri_allow_list` in Supabase Auth config.

If `redirect_to` is NOT in `uri_allow_list`:
- Supabase ignores it without error
- Redirects to `site_url` instead (often the Supabase dashboard or wrong page)
- User sees an unexpected page after Google login
- Email/password login works fine (doesn't use this flow)

## Diagnosis

**Symptom**: Google login redirects to wrong page. Email login works correctly.

**Check**: Supabase Dashboard → Auth → URL Configuration → Redirect URLs

Or via Management API:
```bash
curl -s "https://api.supabase.com/v1/projects/{ref}/config/auth" \
  -H "Authorization: Bearer sbp_..." | jq '.uri_allow_list, .site_url'
```

## Fix

Add your auth server's callback URL to `uri_allow_list`:

```bash
curl -X PATCH "https://api.supabase.com/v1/projects/{ref}/config/auth" \
  -H "Authorization: Bearer sbp_..." \
  -H "Content-Type: application/json" \
  -d '{"uri_allow_list": "https://auth.yourdomain.dev/callback"}'
```

### Key Points

- `uri_allow_list` is for URLs that **Supabase itself** redirects to (OAuth callback)
- NOT for your app's internal callback URLs
- With shared domain cookie SSO, only the auth server's callback is needed
- Comma-separated, no wildcards

## Related

- `site_url` is the fallback when `redirect_to` is missing or not allowed
- `site_url` should be your main app URL (e.g., `https://bsvibe.dev`), not the Supabase dashboard
- Email confirmation links also use `site_url` as base

## Origin

Discovered when Google OAuth login redirected to Supabase dashboard instead of auth.bsvibe.dev/callback. Email login worked fine because it doesn't go through Supabase's authorize endpoint. The `uri_allow_list` had product callback URLs but not the auth server's callback.
