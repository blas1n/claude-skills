---
name: stitch-code-bidirectional-sync
description: Stitch generates screens independently — sidebars/tabs differ per screen. Code must unify, then Stitch must be regenerated to match. One-way sync breaks.
trigger: when applying Stitch designs to a multi-page app, or when user reports "stitch and code don't match"
---

# Stitch-Code Bidirectional Sync

## Problem

Stitch `batch_generate_screens` creates each screen independently. Even with "same sidebar" in the prompt, each screen may generate different navigation items, tab structures, and placeholder content. Applying these directly to code creates inconsistency.

## Anti-pattern: One-way Stitch → Code

```
Stitch Screen A: sidebar = [Dashboard, Neural Network, Security Terminal]
Stitch Screen B: sidebar = [Projects, Board, Architect, Settings]
→ Code applies Screen A to Page A, Screen B to Page B
→ Pages have different sidebars
```

## Correct Pattern: Code-first, then Stitch sync

1. **Define the canonical nav/layout in code** — decide what the real pages and sidebar items are
2. **Apply Stitch visual styling** (colors, typography, card patterns, icons) but NOT the nav structure
3. **Regenerate Stitch screens** with a prompt that specifies the exact sidebar/tabs from code
4. **Verify** — code and Stitch should now match

## Regeneration Prompt Pattern

Include the EXACT sidebar in every screen prompt:
```
"Left sidebar: [Item1 (icon1), Item2 (icon2, ACTIVE), Item3 (icon3)].
This sidebar is IDENTICAL across all pages — do not add or remove items."
```

## Detection

If different pages show different sidebar items, the Stitch screens were generated independently and nav structure was not unified.

## Stitch API Gotchas

### `edit_screens` creates duplicates, not edits
`edit_screens` does NOT modify existing screens in-place. It creates **new copies** of the edited screens. Calling it on 7 screens may result in 14 total (7 original + 7 new). There is no delete API — duplicates must be removed manually via the web UI.

### Dark theme hex values are ignored
`create_design_system` with `colorMode: DARK` + exact hex values in `designMd` does NOT force those colors. Stitch generates its own MD3 palette from the `customColor` seed. Tried: `create_design_system`, `edit_screens` with explicit hex, `generate_screen_from_text` with inline CSS specs, `apply_design_system`, `batch_generate_screens` with `sharedDesignContext`. **All failed** to apply custom dark hex values — Stitch always renders its own light/dark palette.

### `batch_generate_screens` may not persist
`batch_generate_screens` can return `"success": true, "7/7 screens created"` but the screens may not appear in the project (`screenInstances: 0`). The first `batch_generate` on a new project works, subsequent ones may create "draft" screens that need manual acceptance.

### Mitigation
- Use Stitch for **layout/structure reference only** — accept that colors will differ from code
- Code's CSS tokens (index.css) are the source of truth for colors
- If exact visual fidelity is needed, use Playwright screenshots of the running app instead

## Key Insight

Stitch is a design reference, not the source of truth for app structure. The app's routes and navigation are the source of truth. Stitch screens should be regenerated to match code, not the other way around.
