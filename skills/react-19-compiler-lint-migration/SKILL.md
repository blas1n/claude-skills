---
name: react-19-compiler-lint-migration
description: Fix React 19's strict compiler lint rules in legacy React 18 code — set-state-in-effect, react-hooks/purity, Date.now in render. Idiomatic rewrites without useEffect.
version: 1.0.0
task_types: [bugfix, refactor]
---

# React 19 compiler lint migration

React 19 ships stricter lint rules that catch patterns that were common
(and tolerated) in React 18. When they land on an existing codebase via
the React Compiler ESLint plugin, CI suddenly fails on code that runs
fine. This skill lists the patterns and their canonical rewrites.

## `react-hooks/set-state-in-effect`

**What it catches:** `setState()` called synchronously inside a
`useEffect` body. The rule wants effects to sync with external systems,
not derive React state from other React state.

**Common legacy pattern:**

```tsx
// "auto-select first item when list loads"
useEffect(() => {
  if (!selected && items.length > 0) setSelected(items[0].id)
}, [items, selected])
```

**Canonical fix — derive during render with a user-override track:**

```tsx
const [manualSelected, setManualSelected] = useState<string | null>(null)
const selected =
  manualSelected && items.some((i) => i.id === manualSelected)
    ? manualSelected
    : items[0]?.id ?? null
// Pass setManualSelected wherever you used to pass setSelected.
```

The split: `manualSelected` is the user's explicit pick, stored as
React state. `selected` is derived during render with a fallback chain.
When the list changes such that the manual pick is no longer valid,
the derived value silently falls back to the first item.

**Variant — "open this modal when the URL has ?new=1":**

```tsx
// Legacy:
const [createOpen, setCreateOpen] = useState(search.get('new') === '1')
useEffect(() => {
  if (search.get('new') === '1') setCreateOpen(true)
}, [search])

// React 19 — previous-value tracking via state:
const newParam = search.get('new') === '1'
const [createOpen, setCreateOpen] = useState(newParam)
const [prevNewParam, setPrevNewParam] = useState(newParam)
if (prevNewParam !== newParam) {
  setPrevNewParam(newParam)
  if (newParam && !createOpen) setCreateOpen(true)
}
```

React allows conditional `setState` calls *during render* if gated by a
previous-value comparison — it re-renders immediately without effect
overhead. This is the documented pattern for "reset state when a prop
changes."

**Variant — autocomplete menu that opens based on query:**

```tsx
// Legacy:
const [menuOpen, setMenuOpen] = useState(false)
useEffect(() => {
  setMenuOpen(atQuery !== null && candidates.length > 0)
}, [atQuery, candidates.length])

// React 19 — dismissed-flag + derive:
const [menuDismissed, setMenuDismissed] = useState(false)
const menuOpen = !menuDismissed && atQuery !== null && candidates.length > 0

// Reset dismissed on query change (previous-value trick with useRef):
const lastAtQueryRef = useRef(atQuery)
if (lastAtQueryRef.current !== atQuery) {
  lastAtQueryRef.current = atQuery
  if (menuDismissed) setMenuDismissed(false)
}
```

## `react-hooks/purity` — `Date.now()` / `Math.random()` in render

**What it catches:** impure function calls anywhere in the component
render tree — *including inside `useMemo`*. `useMemo` callbacks run
during render; impure calls inside them still violate purity.

**Fix — `useState` lazy initializer:**

```tsx
// Legacy (still flagged by the rule):
const cutoff = useMemo(() => Date.now() - 7 * 86400 * 1000, [])

// React 19 — lazy init runs exactly once at mount:
const [cutoff] = useState(() => Date.now() - 7 * 86400 * 1000)
```

The lazy initializer `() => Date.now() - ...` is *not* part of the render pass — it runs once when the component mounts. That satisfies
the purity rule.

Note: `useMemo(() => ..., [])` is NOT equivalent — the rule still flags
it because `useMemo` callbacks participate in render.

## `react-refresh/only-export-components`

**What it catches:** a file exports both component(s) and non-component
values. Breaks Fast Refresh.

**Fix:** move the non-component export to a separate file. Or, if
colocation is intentional (e.g. an icon registry `const` next to its
helper `Icon` component), scope a disable to the component:

```tsx
// eslint-disable-next-line react-refresh/only-export-components -- reason
function Icon({ ... }) { ... }

export const I = { Home: (...) => <Icon>...</Icon>, ... }
```

## Unused `eslint-disable` directives

After fixing the underlying issue, a previously-needed
`eslint-disable-next-line` comment becomes dead and the compiler flags
it as "Unused eslint-disable directive." Always delete the disable
comment once the refactor resolves the original error.

## Diagnosis workflow

1. `pnpm lint` to get the full list. Fix fundamentals first (unused
   vars, escape characters) — they're one-line changes.
2. `pnpm exec tsc -b` after each fix cluster — removing imports (e.g.
   `useEffect`) can leave nested usages broken; TypeScript catches
   those before you ship.
3. Run `pnpm build` last — it combines both and catches Vite-specific
   issues.

## Anti-patterns

- Don't blanket `eslint-disable-next-line react-hooks/set-state-in-effect`. The rule is nearly always correctly flagging code
  that benefits from the derive-during-render refactor. Scope disables
  to truly imperative patterns only.
- Don't move `Date.now()` inside `useMemo` thinking it satisfies the
  purity rule. It doesn't. Use `useState` lazy init.
- Don't lift "auto-select first" state to the parent just to avoid the
  effect. The derived-state pattern works at any level.
