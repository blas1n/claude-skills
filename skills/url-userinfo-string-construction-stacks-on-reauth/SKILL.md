---
name: url-userinfo-string-construction-stacks-on-reauth
description: Embedding an OAuth/PAT token into an `https://user:pass@host/...` URL via f-string concatenation (`f"https://x-access-token:{token}@{rest}"`) breaks under TWO recurring conditions — (1) the token contains URL-reserved chars (`:` `/` `@` `?` `#` `%`) which the URL parser misreads, and (2) a re-auth on the same checkout (clone-time set-url + a later push-time set-url) STACKS userinfo segments into `user:pass@user:pass@host`. A naive `split("@", 1)` only collapses ONE stack; production needs `rsplit("@", 1)` (or `urllib.parse.urlsplit` + explicit netloc rewrite). Same fix shape across git push, docker registry login, MQTT URIs.
---

# URL userinfo stacking on re-auth + token-special-char breakage

## Symptom triad

`git push` (or any `https://user:pass@host/...` client) fails with one of:

```
fatal: unable to access 'https://x-access-token:***@github.com/...':
  URL rejected: Port number was not a decimal number between 0 and 65535
```

```
fatal: unable to access 'https://x-access-token:***@x-access-token:***@github.com/...':
  URL rejected: Port number was not a decimal number ...
```

```
remote: Invalid username or token. Password authentication is not supported
fatal: Authentication failed for 'https://github.com/...'
```

The error message is curl/libcurl complaining about the URL it just parsed. The token is masked (`***`) so the actual confusing char is invisible — focus on the SHAPE of the userinfo segment, not the token.

## Two distinct bugs, same line of code

```python
def authed_url(repo_url: str, *, token: str) -> str:
    rest = repo_url[len("https://"):]
    return f"https://x-access-token:{token}@{rest}"
```

### Bug 1 — token has URL-reserved chars

GitHub PATs (`ghp_xxx`) only use `[A-Za-z0-9_]` and round-trip safely. OAuth tokens (Connect-with-X flows) carry mixed alphabets including `:` and `/`. A `:` inside the token produces:

```
https://x-access-token:gho_a:b@github.com/owner/repo.git
                              ^ — curl reads as host-port split, says "port not a decimal number"
```

### Bug 2 — re-auth stacks the userinfo

Calling `authed_url` on a URL that ALREADY has userinfo (e.g. `set-url origin` was run with a token at clone time, then `push` reads the origin and re-runs `authed_url` for the current token) produces:

```
https://x-access-token:NEW@x-access-token:OLD@github.com/owner/repo.git
                          ^ first @          ^ second @
```

curl reads the first `@` as the userinfo boundary, then the second `:` (after `x-access-token` in `OLD@host`) as host-port. Same "port not decimal" error from a different cause.

## The fix that handles BOTH

```python
from urllib.parse import quote

def authed_url(repo_url: str, *, token: str | None) -> str:
    if not token or not repo_url.startswith("https://"):
        return repo_url
    rest = repo_url[len("https://"):]
    # rsplit handles 0, 1, or N already-present userinfo stacks — collapse
    # to the host portion alone. quote('@', safe='') guarantees a real
    # token cannot contain raw '@' so the LAST '@' is unambiguously the
    # userinfo terminator.
    if "@" in rest:
        rest = rest.rsplit("@", 1)[1]
    return f"https://x-access-token:{quote(token, safe='')}@{rest}"
```

Two layers:
1. `quote(token, safe='')` percent-encodes every reserved char.
2. `rsplit("@", 1)` collapses any number of stacked userinfo segments.

A naive `split("@", 1)` only strips ONE userinfo layer; if the origin URL already has TWO (e.g. a prior failed push left both), the second pass embeds NEW on top of OLD again.

## Safer alternative — proper URL parser

```python
from urllib.parse import quote, urlsplit, urlunsplit

def authed_url(repo_url: str, *, token: str | None) -> str:
    if not token:
        return repo_url
    parts = urlsplit(repo_url)
    if parts.scheme != "https":
        return repo_url
    # Strip any userinfo from netloc — split on the LAST '@' so stacked
    # userinfo collapses; one-shot URLs (no '@' at all) round-trip unchanged.
    netloc = parts.netloc.rsplit("@", 1)[-1]
    new_netloc = f"x-access-token:{quote(token, safe='')}@{netloc}"
    return urlunsplit((parts.scheme, new_netloc, parts.path, parts.query, parts.fragment))
```

Slower but unambiguous. Recommended when the surrounding codebase is willing to take the import.

## TDD that catches both regressions

Three tests, one for each named failure mode, pin the wire shape:

```python
def test_authed_url_percent_encodes_token_special_chars():
    out = ops.authed_url("https://github.com/owner/repo.git", token="gho_a:b/c%d")
    assert "gho_a:b/c%d" not in out  # raw chars MUST NOT appear in userinfo
    assert "%3A" in out and "%2F" in out and "%25" in out

def test_authed_url_idempotent_on_already_authed_url():
    once = ops.authed_url("https://github.com/owner/repo.git", token="ghp_one")
    twice = ops.authed_url(once, token="ghp_two")
    assert twice.count("x-access-token:") == 1
    assert "ghp_one" not in twice and "ghp_two" in twice

def test_authed_url_strips_doubled_userinfo():
    doubled = "https://x-access-token:OLD@x-access-token:OLD@github.com/owner/repo.git"
    fixed = ops.authed_url(doubled, token="NEW")
    assert fixed.count("x-access-token:") == 1
    assert "OLD" not in fixed
```

## Same shape, other surfaces

The pattern is not git-specific. Anywhere a token gets embedded into a URL via string formatting:

- **Docker registry login**: `docker login https://user:pass@registry.example.com` — same userinfo, same trap on token rotation.
- **MQTT URIs**: `mqtt://user:pass@broker:1883` — extra fun because the host already has `:port`.
- **PostgreSQL DSN**: `postgresql://user:pass@host:5432/db` — token with `@` in password.
- **AMQP / Redis**: same userinfo trap when credentials rotate.

If you find an f-string URL construction with `:` `@` `{}` in the same line, audit it for both bugs.

## Origin

BSVibe E42-E44 dogfood (2026-06-17/18). The git push delivery (`backend/workflow/infrastructure/delivery/git_ops.py`) hit Bug 1 first when an OAuth token entered the system, then E43's `split("@", 1)` partial fix surfaced Bug 2 the next iteration because the run's git config retained the stale userinfo from a previous attempt. E44 converged on `rsplit` after a triple-layer URL surfaced in the prod dogfood retrace. The shape repeats in every URL-userinfo embedding seam — fix in one place, audit the others.
