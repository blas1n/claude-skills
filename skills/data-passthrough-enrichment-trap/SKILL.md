---
name: data-passthrough-enrichment-trap
description: Adding metadata to a data passthrough layer (gateway, middleware, router) by wrapping the original payload breaks all downstream consumers — use flat merge instead
version: 1.0.0
---

# Data Passthrough Enrichment Trap

## Problem

When a middleware/gateway layer needs to add metadata (signatures, raw bytes, headers) to a payload before passing it downstream, the instinct is to wrap the original data:

- Symptom: Existing downstream consumers silently stop finding their expected keys in the payload
- Root cause: Wrapping (`{"body": original, "meta": extra}`) moves all original keys one level deeper
- Common mistake: Only testing the one consumer that needs the new metadata, missing all others that read the payload directly

## Solution

Use flat merge to add metadata keys alongside the original payload:

1. Identify all downstream consumers of the data passthrough
2. Merge metadata as top-level keys into the original payload instead of wrapping
3. Use `setdefault()` to avoid overwriting keys that already exist in the payload

```python
# WRONG — wrapping breaks existing consumers
webhook_data = {
    "body": original_payload,       # existing keys now nested
    "raw_body": raw_bytes,
    "headers": {"x-sig": sig},
}

# RIGHT — flat merge preserves existing keys
if isinstance(body, dict):
    body.setdefault("raw_body", raw_bytes)
    if sig:
        body.setdefault("x-hub-signature-256", sig)
# All existing consumers still find their keys at the top level
# New consumers can read the added metadata keys
```

## Key Insights

- A passthrough layer's contract is **implicit** — every downstream consumer defines their own expected shape. Wrapping silently breaks all of them without compile-time or test-time errors (unless integration tests cover every consumer).
- `setdefault()` is critical: it prevents the metadata keys from overwriting legitimate payload keys with the same name.
- This trap is especially dangerous in plugin architectures where new plugins are added independently and the gateway author doesn't know all consumers.

## Red Flags

- Adding a wrapper dict around an existing passthrough payload ("let me restructure this to be cleaner")
- Only one consumer needs the new metadata, but the passthrough serves many
- Tests pass because they construct `input_data` manually with the new structure, but no integration test sends real HTTP requests through the gateway
- The data flows through a generic interface like `context.input_data` that multiple independent modules read
