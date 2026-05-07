---
name: json-cache-uuid-key-type-drift
description: When list_X comes from a JSON cache (UUID→str) but related rows come fresh from the DB (still UUID), dict[record["id"]] lookups silently miss. Symptom — first request after deploy works, all later requests behave as if related rows are empty.
version: 1.0.0
category: trap
---

# JSON Cache UUID Key Type Drift Trap

## Problem

You have a parent table (`rules`) and a child table (`rule_conditions`) joined on `rule_id`. To avoid N+1, the API endpoint:

1. Fetches all rules (cached)
2. Fetches all conditions for the tenant (uncached)
3. Builds `cond_by_rule[c["rule_id"]] = ...` — keyed by UUID from asyncpg
4. For each rule, looks up `cond_by_rule.get(rule["id"])`

**On a cache miss**, both `rule["id"]` and `c["rule_id"]` are `UUID` objects → lookup hits.
**On a cache hit**, `rule["id"]` was JSON-serialized (`UUID → str`) and is now a `str`. The lookup against UUID-keyed dict misses → the rule is rendered with **empty conditions**.

증상:
- "Works the first time after `pkill app`, breaks after that" — classic cache-warmup vs cache-hit divergence
- Rule engine with `match_all` semantics on conditions (empty AND-loop returns `True`) → priority-1 rule wins for **every** input regardless of payload
- Tests pass because they mock `list_rules` to return raw asyncpg-style UUID dicts, which matches the no-cache path
- Rules listing (`GET /rules`) shows the conditions correctly but the engine endpoint (`POST /rules/test`) doesn't — they live in different functions and only one normalises types

## Root cause

The cache (e.g. Redis via `CacheManager` with `json.dumps` + a `_CacheEncoder` that maps `UUID → str`) does **not** preserve the original type. After `json.loads`, a previously-`UUID` field is a `str`. Dict lookups in Python are type-strict — `dict[UUID(...)]` and `dict["..."]` are different keys.

```python
>>> from uuid import UUID, uuid4
>>> u = uuid4()
>>> d = {u: "v"}
>>> d.get(str(u))
None  # silent miss
```

## Solution

**Normalise both sides to `str` at the boundary** between cache-or-DB and the lookup:

```python
# Build the lookup table by str(rule_id)
all_conditions = await repo.list_conditions_for_tenant(tenant_id)
cond_by_rule: dict[str, list] = defaultdict(list)
for c in all_conditions:
    cond_by_rule[str(c["rule_id"])].append(c)

# Look up by str(r["id"]) — works whether r came from cache (already str)
# or fresh from DB (UUID, gets stringified here).
for r in rule_rows:
    conditions = cond_by_rule.get(str(r["id"]), [])
    ...
```

Picking `str` is more forgiving than `UUID(r["id"])` — it accepts both already-string keys and UUID objects, and never raises on malformed inputs.

### Regression test

Mock-based unit tests miss this because the mock typically returns the same shape as a fresh fetch. Force the cached shape explicitly:

```python
cached_rule = _rule_row(...)
# Simulate post-cache: id and tenant_id are str, datetimes are isoformat
cached_rule["id"] = str(cached_rule["id"])
cached_rule["tenant_id"] = str(cached_rule["tenant_id"])
cached_rule["created_at"] = cached_rule["created_at"].isoformat()
# ...
condition = {"rule_id": rule_uuid, ...}  # UUID — fresh from DB

with patch("...list_rules", return_value=[cached_rule, default_rule]), \
     patch("...list_conditions_for_tenant", return_value=[condition]):
    resp = client.post(f"/api/v1/tenants/{tid}/rules/test", json={...})
    # Without the str-normalised lookup the priority-1 rule would match
    # unconditionally; with the fix it falls through to default.
    assert resp.json()["matched_rule"]["priority"] != 1
```

## Key insights

- A "rules engine" with **AND-of-zero-conditions returns True** is a common, reasonable default — but combined with type-drift on the conditions lookup, it makes every rule unconditionally match. Look at this combo whenever a routing/policy engine "always matches the highest-priority rule."
- The bug only surfaces when:
  - The cache has been populated (i.e. **after** the first request, not on cold boot)
  - **AND** the parent table is cached
  - **AND** the child table is not, *or* is cached separately
- Existing list endpoints often have this fix already (someone debugged it once for `GET /rules`), but the same parent+child pattern in a different endpoint (`POST /rules/test`, batch evaluators, …) silently re-introduces it. **Grep for `cache_key_*` callers and audit each lookup site individually.**
- The `_CacheEncoder` cleanly handling UUID/datetime is what makes this so silent — there's no JSON serialization error to catch your eye.

## Red flags

- "Works after restart, breaks immediately on second request"
- "All routing decisions land on the same priority-1 rule no matter what we send"
- The endpoint that listing rules (with conditions) shows them correctly but the endpoint that *evaluates* them acts as if they have none
- A `defaultdict[UUID, list]` initialised right before a `dict.get(record["id"])` lookup

## Related

- `~/.claude/skills/asyncpg-testing-patterns` — tests that mock at repository level avoid this trap if the mock is faithful
- `~/.claude/skills/mock-fixtures-hide-wiring-bugs` — same family: integration tests with real cache + real DB catch what mocked tests miss
