---
name: npx-bin-package-resolution
description: npx resolves package names, not binary names — binaries defined inside a package require -p flag or the package name itself
---

# npx Binary vs Package Name Resolution

## The Trap

A package (`stitch-mcp-auto`) can define multiple `bin` entries in `package.json`:

```json
{
  "name": "stitch-mcp-auto",
  "bin": {
    "stitch-mcp-auto": "index.js",
    "stitch-mcp-auto-setup": "setup.js"   ← binary name ≠ package name
  }
}
```

Running `npx stitch-mcp-auto-setup` fails with 404 because npx looks for a **package** named `stitch-mcp-auto-setup`, which doesn't exist.

```bash
npx stitch-mcp-auto-setup
# npm error 404 Not Found - GET https://registry.npmjs.org/stitch-mcp-auto-setup
```

## The Fix

Use `-p` to specify the package, then name the binary:

```bash
npx -p stitch-mcp-auto stitch-mcp-auto-setup
```

Or just use the package name when package name == binary name:

```bash
npx stitch-mcp-auto        # works: package name = binary name
npx stitch-mcp-auto-setup  # fails: binary inside a different package
```

## Diagnosis

Before running `npx <something>`, verify:

```bash
# Check if it's a package on npm
npm view <something> version

# Check if it's a binary inside another package
npm view <package> bin
# If bin includes <something>, use: npx -p <package> <something>
```
