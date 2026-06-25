---
name: diff-viewer-hunk-requires-full-headers
description: React/JS diff-render libraries (@git-diff-view/react, react-diff-view, diff2html) that take a `hunks`/diff-string input silently render NOTHING when fed a bare `@@ … @@` hunk — they need the full `diff --git` / `--- ` / `+++ ` file headers. A bare hunk parses as zero changes. Mocking the library in component tests hides this; validate the hunk format with a real (unmocked) parse test.
when_to_use: Feeding a third-party diff/patch renderer a unified diff you built or sliced yourself — a captured `git diff`, a per-file split, or a synthesized all-additions hunk for a no-before file. Especially when the rendered diff comes up empty in the browser but your tests are green.
languages: [typescript, javascript]
frameworks: [react, "@git-diff-view/react", react-diff-view, diff2html, next.js]
---

# Diff-render libraries need the FULL diff section, not a bare hunk

## Symptom

A React diff component renders **blank** (no added/removed lines) for some files
even though you passed it a valid-looking unified-diff hunk — while your
component tests are all green. Typically the *captured* `git diff` renders fine
but a **synthesized** or **header-stripped** hunk renders empty.

## Root cause

These libraries parse the diff input expecting a full file section:

```
diff --git a/path b/path
new file mode 100644          (or: index <old>..<new> <mode>)
--- /dev/null                 (or: --- a/path)
+++ b/path
@@ -0,0 +1,N @@
+line one
+line two
```

If you hand them only the **hunk body**:

```
@@ -0,0 +1,N @@
+line one
+line two
```

the parser finds no file headers, attributes the `@@` lines to no file, and
yields **zero** changes — `DiffFile.additionLength === 0`. It does not throw; it
renders an empty pane. For `@git-diff-view/react`, `data.hunks: string[]`
elements must each be a full `diff --git …` section.

## Why tests miss it (the real trap)

Component tests usually **mock** the heavy diff library (it's slow / async-highlights
/ noisy in jsdom):

```ts
vi.mock("@git-diff-view/react", () => ({ DiffView: ({data}) => <pre>{data.hunks.join("\n")}</pre>, ... }))
```

The mock happily echoes whatever string you passed, so `+line one` appears in the
DOM and the assertion passes — but the **real** library would have parsed it to
nothing. The mock validates *your* code, never the **format contract** between
your adapter and the library. This is a specific case of
[[mock-fixtures-hide-wiring-bugs]] / [[test-against-source-contracts]].

## Fix

1. **Synthesize a full section**, headers included — for an all-additions
   (no-before) file:

   ```ts
   export function synthesizeAdditionHunk(fileName: string, content: string): string {
     const lines = content.split("\n");
     if (lines.length > 1 && lines.at(-1) === "") lines.pop(); // drop trailing-newline phantom
     const body = lines.map((l) => `+${l}`).join("\n");
     return [
       `diff --git a/${fileName} b/${fileName}`,
       "new file mode 100644",
       "--- /dev/null",
       `+++ b/${fileName}`,
       `@@ -0,0 +1,${lines.length} @@`,
       body,
     ].join("\n");
   }
   ```

   When you split a multi-file `git diff` per file, keep each file's **entire**
   `diff --git …` section as the hunk string — don't strip to the `@@` body.

2. **Guard the format with a REAL (unmocked) parse test** — construct the
   library's own model and assert the change counts, so a format regression
   fails in CI instead of rendering blank in prod:

   ```ts
   import { DiffFile } from "@git-diff-view/react"; // vitest resolves the nested pkg

   const f = DiffFile.createInstance({
     oldFile: { fileName }, newFile: { fileName }, hunks: [section],
   });
   f.initRaw();
   f.buildUnifiedDiffLines();
   expect(f.additionLength).toBe(expectedAdds);
   expect(f.deletionLength).toBe(expectedDels);
   ```

   This caught the bug the mock hid: a bare hunk → `additionLength === 0`.

## Generalization

Any time you build/slice a structured payload for a third-party renderer or
parser (unified diff, ICS, MIME, a wire protocol), the mock you use to keep
component tests fast cannot vouch for the payload's validity. Add one **real**
round-trip test that feeds the payload to the actual library and asserts the
parsed result — the cheapest insurance against "green tests, blank screen."
