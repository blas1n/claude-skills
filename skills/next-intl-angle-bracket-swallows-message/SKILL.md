---
name: next-intl-angle-bracket-swallows-message
description: next-intl / ICU treats `<name>` in a message as a rich-text tag, so prose that mentions a CLI placeholder (`claude mcp add bsvibe <url>`) fails to parse with INVALID_MESSAGE UNCLOSED_TAG and the UI renders nothing where the sentence should be. Nothing crashes, no test fails — the copy is just silently missing.
category: trap
---

# next-intl: an angle bracket in prose swallows the whole message

## Problem

Message catalogues are plain strings, so writing a placeholder the way CLI docs
do feels harmless:

```json
"configHint": "Add this entry to `~/.config/claude-code/mcp.json` (or run `claude mcp add bsvibe <url>`). The CLI handles the OAuth dance…"
```

next-intl parses messages as ICU MessageFormat **with rich-text tags**, so
`<url>` opens a tag that never closes:

```
IntlError: INVALID_MESSAGE: UNCLOSED_TAG (Add this entry to `~/.config/…`)
```

What makes it expensive:

- **Nothing throws.** next-intl reports through `onError` and renders the error
  string (or the key) in place of the sentence.
- **No test fails.** Component tests assert on *other* text; the broken message
  is only logged. In one case the error was printed six times per test run for
  months and read as noise.
- **The screen looks fine at a glance** — a hint paragraph is simply absent,
  which is exactly what an empty state looks like.

Any `<…>` in copy does it: `<url>`, `<your-token>`, `<project>`, `<branch>`.
Not just placeholders — `a < b` and `->` written as `<-` hit it too.

## Solution

### 1. Don't write angle brackets in copy

Use square brackets, which are ICU-inert and are also a common CLI-doc
convention:

```json
"configHint": "… (or run `claude mcp add bsvibe [url]`)…"
```

Escaping via ICU apostrophes (`'<url>'`) also works but is fragile — the
apostrophe itself then becomes significant, and translators will not preserve
it.

### 2. Guard the whole catalogue, not the one message you found

The trap is a property of writing copy, so the next occurrence will be written
by someone who never saw this bug. Walk every leaf key through the **real**
parser — `createTranslator` is what next-intl uses at runtime, so it catches
exactly what production would:

```ts
import { createTranslator } from "next-intl";
import en from "../messages/en.json";
import ko from "../messages/ko.json";

function leafKeys(node, prefix = "") {
  return Object.entries(node).flatMap(([k, v]) => {
    const path = prefix ? `${prefix}.${k}` : k;
    return typeof v === "string" ? [path] : leafKeys(v, path);
  });
}

function unparseable(locale, messages) {
  const broken = [];
  let current = "";
  const t = createTranslator({
    locale,
    messages,
    onError(error) {
      // MISSING_FORMAT_VALUE just means we called a parameterised message with
      // no values — not a defect in the message itself.
      if (error.code === "INVALID_MESSAGE") broken.push(`${current} — ${error.message}`);
    },
  });
  for (const key of leafKeys(messages)) {
    current = key;
    try { t(key); } catch { /* formatting failure, already seen by onError */ }
  }
  return broken;
}

it.each([["en", en], ["ko", ko]])("%s parses", (locale, m) =>
  expect(unparseable(locale, m)).toEqual([]));
```

Filter to `INVALID_MESSAGE`. Calling `t("x.y")` without values for `{days}`
raises a *different* code and is not a defect — assert on parse failures only.

While you are there, assert both locales expose the same leaf keys; the same
walk gives it for free and catches half-translated additions.

## Detection in an existing repo

```bash
grep -o '<[a-z_][a-z0-9_-]*>' apps/pwa/messages/en.json | sort | uniq -c
pnpm vitest run <any-component-test> 2>&1 | grep -c UNCLOSED_TAG
```

A non-zero count in a test you did not touch means the defect is pre-existing —
report it as such rather than folding the fix into unrelated work.

## Related

- `vitest-restoreallmocks-wipes-factory-mock` — the other "error is logged, assertion fails elsewhere" reader trap
- `bsvibe-report-output-language-localization`
