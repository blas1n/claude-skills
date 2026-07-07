---
name: upstream-repo-rename-silent-hardcoded-fallback
description: When you depend on a 3rd-party GitHub-hosted data artifact (CSV/JSON/schema/config) via `try: fetch new; except: use HARDCODED_DEFAULT_URL`, the "safety fallback" masks upstream file renames. Symptom — after upstream restructures naming, the auto-discovery quietly returns nothing (regex mismatch = empty result), the code falls through to the frozen default URL, that URL 404s, and the caller catches the exception and degrades to `whitelist=set()` / empty result / None — silently. No hard error, but every downstream measurement built on that data reshapes. bloasis PR59 caught this after 4 weeks of `whitelist=0` had already re-run the mention extractor with distorted sample sizes across per-bucket tables.
category: trap
---

# Upstream repo rename → silent hardcoded-default fallback

## Problem

A common pattern for 3rd-party GitHub-hosted data (e.g. `fja05680/sp500`
membership CSV, LLM tokenizer configs, GeoJSON boundaries, tax-rate
tables, license lists):

```python
DEFAULT_DATASET_URL = "https://raw.githubusercontent.com/fja05680/sp500/master/S%26P%20500%20Historical%20Components%20%26%20Changes(02-21-2025).csv"
_DATED_CSV_RE = re.compile(r"S&P 500 Historical Components & Changes\((\d{2})-(\d{2})-(\d{4})\)\.csv$")

def _resolve_dataset_url() -> str:
    if url := os.environ.get("MY_URL"): return url
    try:
        entries = httpx.get(GITHUB_CONTENTS_API_URL).json()
    except httpx.HTTPError:
        return DEFAULT_DATASET_URL          # ← trap 1: net failure fallback
    best_url = None
    for e in entries:
        if _DATED_CSV_RE.match(e["name"]):  # ← trap 2: regex expects OLD naming
            ...
    return best_url or DEFAULT_DATASET_URL  # ← trap 3: empty result falls back too
```

Three fallback layers converging on the same hardcoded URL feels like
defense-in-depth. It's actually a **single point of silent failure**.
When the upstream repo restructures its files (rename, split into
`(Updated).csv` + frozen `.csv`, move under a subdirectory), the regex
matches nothing, `best_url` stays `None`, the resolver returns
`DEFAULT_DATASET_URL`, that URL is now 404, and the download raises
`RuntimeError` — which most callers swallow to keep operating:

```python
def load_whitelist() -> set[str]:
    try:
        return {t.upper() for t in list_sp500(cache_dir=...)}
    except Exception:            # ← "graceful degradation"
        return set()             # empty
```

Now every downstream computation that intersects `content` with this
whitelist quietly loses coverage. In bloasis PR59, this reshaped the
mention-tracking corpus from ~600 to 328 events, with per-bucket
counts (n_overnight: 105→18, n_after_hours: 24→30) shifting the
apparent "edge" cell from +1.32% neg+OOT to +0.40%. The pipeline kept
running; the daily cron kept logging "whitelist size: 0" harmlessly;
retrospective comparisons drew wrong conclusions from the drifted
sample.

## Detection

Three signals — any one triggers investigation:

1. **Downstream size gap that "moves the story"**. If a measurement
   built on this data suddenly drops sample count by ≥20% between
   comparable runs, do NOT ascribe the drop to "cleaner data" until
   you've confirmed the upstream fetch actually landed a full payload.
2. **Log lines like `whitelist size: 0` / `returned 0 rows`** where
   the last-known state was 500. Zero is not a plausible business
   value; it's the signature of the graceful-degradation catch.
3. **A hardcoded default URL that's more than a few months old**.
   Upstream repos rename or restructure on their schedule. If you
   haven't touched the default URL string in the current release, it's
   probably stale.

## Diagnostic probe (30 seconds)

Bypass the graceful-degradation catch and see the raw failure:

```python
import httpx
# 1. Direct-fetch DEFAULT_DATASET_URL — does the frozen URL still exist?
r = httpx.get(DEFAULT_DATASET_URL, follow_redirects=True, timeout=10)
print("default:", r.status_code)

# 2. Direct-fetch the discovery API — what does it currently list?
r = httpx.get(GITHUB_CONTENTS_API_URL, follow_redirects=True, timeout=10)
print("api:", r.status_code, [e["name"] for e in r.json() if "csv" in e["name"].lower()])
```

If default 404s AND the API lists files that don't match your regex,
you have this bug.

## Solution

Two layers, both important:

### 1. Make the resolver rank-and-order, not regex-and-hope

Don't rely on a single regex that fails silently. List the naming
schemes you expect in priority order and score each API entry:

```python
_UPDATED = "S&P 500 Historical Components & Changes (Updated).csv"
_BARE    = "S&P 500 Historical Components & Changes.csv"
_DATED_RE = re.compile(r"^S&P 500 Historical Components & Changes\((\d{2})-(\d{2})-(\d{4})\)\.csv$")

def _resolve() -> str:
    ...
    for entry in entries:
        name = entry["name"]
        if name == _UPDATED:            rank = (1, ())
        elif name == _BARE:             rank = (2, ())
        elif (m := _DATED_RE.match(name)):
            month, day, year = map(int, m.groups())
            rank = (3, (-year, -month, -day))   # latest date wins tiebreak
        else:                           continue
        ...
```

When a fourth naming scheme lands upstream, the resolver returns
`None` cleanly — and the caller can raise a distinguishable error
instead of silently returning the stale default.

### 2. Loud downstream sanity check

The graceful-degradation catch in the caller is the second half of
the silent-failure conspiracy. Add a floor:

```python
def load_whitelist() -> set[str]:
    tickers = list_sp500(cache_dir=...)   # let it raise on total failure
    if len(tickers) < 400:
        raise RuntimeError(
            f"SP500 whitelist too small ({len(tickers)}): "
            "upstream artifact may have renamed. "
            "Check DEFAULT_DATASET_URL, or set SP500_HISTORICAL_URL."
        )
    return {t.upper() for t in tickers}
```

If you MUST swallow errors for uptime reasons (e.g. daily cron),
emit a distinct log level (`ERROR`, not `INFO`) and increment a
metric your daily glance actually reads. `whitelist: 0` in the same
INFO stream as normal progress is invisible.

## What NOT to do

- Do not just update `DEFAULT_DATASET_URL` to the current file and
  move on. The root cause is the fallback pattern; a future rename
  reintroduces the same silent-degradation window.
- Do not add a third and fourth fallback URL. Each additional layer
  broadens the window during which the pipeline "works" on stale or
  degraded data.
- Do not treat "empty whitelist / empty ticker set / empty result"
  as a valid output. If your data source can legitimately return
  zero, encode that in a separate sentinel; overloading empty with
  "silently degraded" is what buys the 4-week undetected window.

## Compounding pattern: repository restructures are recurring

A GitHub-hosted CSV that once had one filename can, over time:
- Split into (Updated) + frozen snapshot (this case)
- Move under a subdirectory (`data/sp500-*.csv`)
- Migrate to LFS (raw.githubusercontent.com stops serving the bytes)
- Move to a different repo (org fork, license change)
- Be replaced by a JSON schema (different `_parse_dataset` breaks silently)

Assume it. Any hardcoded-URL string in your code that references a
3rd-party repo is a **time bomb with the maintainer's schedule**. The
best-practice minimum is a runtime `probe → raise` at import time or
at the start of each cron run, not "try new, fall back to old, catch,
return empty".

## Related traps

- [[sqlite-naive-datetime-system-tz-silent-shift]] — different mechanism,
  same shape: silent data-shape shift downstream that only manifests
  as changed aggregate numbers, not a crash.
- [[external-cli-wrapper-contract-drift]] — external CLI contract drift.
  Distinct: that trap is about subprocess/HTTP wrappers where the
  boundary is mocked in tests. This trap is about live data-fetch
  fallback where the boundary is real but the *content* silently shifts.
