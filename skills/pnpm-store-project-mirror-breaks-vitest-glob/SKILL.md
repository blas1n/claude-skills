---
name: pnpm-store-project-mirror-breaks-vitest-glob
description: After `pnpm install` in a git worktree, vitest/jest can discover a test file from a SECOND path — pnpm hardlinks the whole project (test/ included) into `~/Library/pnpm/store/v<n>/projects/<hash>/`, and the glob picks up that out-of-root mirror where the `@/` alias / vite root doesn't apply → bogus "Cannot find package '@/...'" resolution errors. Clearing the stale store-project mirror fixes it.
when_to_use: A worktree's test suite suddenly fails to RESOLVE imports (`Cannot find package '@/...'`, alias not applying) for a NEW or just-touched test file while sibling tests in the same dir pass — especially right after a fresh `pnpm install` / `pnpm install --frozen-lockfile` in that worktree. Also when a test "Failed Suite" is reported from a `~/Library/pnpm/store/.../projects/<hash>/...` path you never wrote to.
languages: [typescript, javascript]
frameworks: [vitest, jest, pnpm, vite, next.js]
---

# pnpm's project hardlink mirror makes vitest glob a test from outside the root

## Symptom

In a git worktree, after `pnpm install`, the test runner reports the SAME test
file failing from two paths — the real one and a store path:

```
FAIL  apps/pwa/test/foo.test.tsx
FAIL  Library/pnpm/store/v10/projects/<hash>/test/foo.test.tsx
Error: Cannot find package '@/components/...' imported from .../test/foo.test.tsx
```

Sibling tests in the same directory (with the identical `import X from "@/..."`)
pass. Only a **new or recently-written** test file trips it. tsc/biome are fine;
it's purely a test-discovery/alias-resolution error.

## Root cause

`pnpm install` content-addresses the project and **hardlinks the entire project
tree — including `test/` — into `~/Library/pnpm/store/v<n>/projects/<hash>/`**
(the per-project side-effects store, hash derived from the project). Those are
hardlinks (same inode), not symlinks, so they're real files at a second path.

The test runner's file glob (vitest `include: ["test/**/*.test.{ts,tsx}"]`,
resolved against the vite `root`) ends up discovering the file via that
out-of-root store path. There, the `@` alias — defined as
`fileURLToPath(new URL("./", import.meta.url))` = the project dir — and vite's
"allowed root" don't cover the store location, so `@/...` resolves to nothing →
"Cannot find package". The reason a *fresh* file triggers it is link/glob
ordering; older files happen to resolve to the in-root copy.

Confirm with an inode compare:

```bash
ls -i test/foo.test.tsx
ls -i ~/Library/pnpm/store/v10/projects/<hash>/test/foo.test.tsx   # SAME inode → hardlink mirror
```

## Fix

Delete the stale store-project mirror. It's hardlinks — removing the store copy
does NOT touch your real working-tree files (the other hardlink survives):

```bash
rm -rf ~/Library/pnpm/store/v10/projects/<hash>
npx vitest run test/foo.test.tsx     # now a single, in-root path → @/ resolves
```

(Find `<hash>` from the failing path in the runner output, or
`ls ~/Library/pnpm/store/v*/projects/`.)

## Prevention

- **Run the test suite against a symlinked `node_modules`, not a fresh in-worktree
  `pnpm install`.** Symlinking the worktree's `node_modules` to a sibling
  worktree that has the same deps (e.g. `ln -s ../../main/apps/pwa/node_modules
  node_modules`) avoids creating the project store mirror entirely. Do the real
  `pnpm install` only when you need a real `node_modules` for the production
  build (`next build` rejects the symlink — see below), and clear the mirror
  afterward if you then run tests.
- The symlink trick is also why `next build` (Turbopack) fails with
  "Symlink node_modules is invalid, it points out of the filesystem root" — so
  the usual pattern is: **symlink for tests, real install for build.** Just
  remember the real install plants the store mirror.
- This is worktree-specific: multiple worktrees of the same package share the
  same project hash, so one worktree's install can leave a mirror that another
  worktree's runner then globs.

## Generalization

Any content-addressed package manager (pnpm, and Bun's global cache) can create
hardlinked copies of your source outside the project root. When a glob-based tool
(test runner, linter, bundler) reports a file from a `store`/`cache` path you
never wrote, suspect a hardlink mirror — `ls -i` to confirm the shared inode, and
delete the out-of-root copy rather than your real files.
