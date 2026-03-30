---
name: playwright-headless-missing-fonts
description: "Playwright elements report 'hidden' in minimal Docker containers because no system fonts are installed — text has zero rendered dimensions"
version: 1.0.0
---

# Playwright "Hidden" Elements: Missing Fonts in Minimal Containers

**Problem**: Playwright's `toBeVisible()` fails on ALL text elements with `Expected: visible, Received: hidden`, even though the accessibility tree shows correct text content. The element resolves to the right DOM node, but Playwright considers it hidden.

**Root Cause**: Minimal Docker images (`python:3.11-slim`, `node:alpine`, `ubuntu-minimal`) have **zero fonts installed**. When Chromium can't find any font to render text, the text has zero rendered dimensions → Playwright's visibility check (`offsetWidth > 0 && offsetHeight > 0`) fails.

---

## Symptom Recognition

```
Error: expect(locator).toBeVisible() failed
Locator: getByText('Dashboard')
Expected: visible
Received: hidden

- 9 × locator resolved to <h1 class="text-xl font-bold">Dashboard</h1>
  - unexpected value "hidden"
```

**Key indicators**:
- Element **resolves** correctly (it's in the DOM)
- Text content matches
- But visibility is "hidden"
- ALL text-based assertions fail, not just one
- SVG icons/images still render fine
- Screenshots show a dark page with icons but no visible text

**Not the cause if**: Only some text elements are hidden (that's a CSS/layout issue, not fonts).

---

## Diagnosis

```bash
# Check if ANY fonts exist
fc-list 2>/dev/null | head -5
ls /usr/share/fonts/ 2>/dev/null
ls /home/*/.fonts/ 2>/dev/null

# If all return empty → this is the problem
```

---

## Fix 1: Add Fonts to Dockerfile (Best)

```dockerfile
# For Debian/Ubuntu-based images
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

# For Alpine
RUN apk add --no-cache fontconfig ttf-dejavu
```

---

## Fix 2: Install Fonts Without Root (micromamba)

When you can't modify the Dockerfile or don't have root:

```bash
# Install micromamba (user-space package manager)
# For x86_64:
curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj bin/micromamba
# For aarch64:
curl -Ls https://micro.mamba.pm/api/micromamba/linux-aarch64/latest | tar -xvj bin/micromamba

# Install fonts + fontconfig
export MAMBA_ROOT_PREFIX=$HOME/.mamba
./bin/micromamba create -n pw-deps -c conda-forge -y \
    fonts-conda-forge font-ttf-dejavu-sans-mono fontconfig

# Symlink to user fonts directory
mkdir -p ~/.fonts
ln -sf $MAMBA_ROOT_PREFIX/envs/pw-deps/fonts/* ~/.fonts/

# Configure fontconfig
mkdir -p ~/.config/fontconfig
cat > ~/.config/fontconfig/fonts.conf << 'EOF'
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <dir prefix="home">.fonts</dir>
</fontconfig>
EOF

# Update cache
$MAMBA_ROOT_PREFIX/envs/pw-deps/bin/fc-cache -f
```

Then set env vars when running Playwright:
```bash
FONTCONFIG_PATH=~/.config/fontconfig \
FONTCONFIG_FILE=~/.config/fontconfig/fonts.conf \
npx playwright test
```

Or configure in `playwright.config.ts`:
```typescript
use: {
  launchOptions: {
    env: {
      ...process.env,
      FONTCONFIG_PATH: resolve(homedir(), '.config/fontconfig'),
      FONTCONFIG_FILE: resolve(homedir(), '.config/fontconfig/fonts.conf'),
    },
  },
},
```

---

## Related: Missing System Libraries (libgbm, libcups, etc.)

Chromium also needs system shared libraries. In restricted containers, you can:

1. Install most via micromamba: `glib nss nspr dbus atk at-spi2-core libxcb libxkbcommon xorg-libx11 xorg-libxcomposite xorg-libxdamage xorg-libxext xorg-libxfixes xorg-libxrandr libdrm cairo pango alsa-lib`

2. For libs not in conda-forge (libgbm, libcups), create minimal stubs:
```c
// stub.c — provides symbols without real implementation
// Sufficient for headless Chromium
#include <stddef.h>
#include <stdint.h>
typedef struct gbm_device gbm_device;
typedef struct gbm_bo gbm_bo;
union gbm_bo_handle { void *ptr; int32_t s32; uint32_t u32; int64_t s64; uint64_t u64; };
gbm_bo *gbm_bo_create(gbm_device *d, uint32_t w, uint32_t h, uint32_t f, uint32_t fl) { return NULL; }
// ... all required symbols with no-op implementations
```
```bash
gcc -shared -o $CONDA_LIB/libgbm.so.1 stub.c -Wl,-soname,libgbm.so.1
```

Set `LD_LIBRARY_PATH` to include the conda lib directory.

---

## Checklist

- [ ] Check `fc-list` — if empty, fonts are the problem
- [ ] Install DejaVu Sans (good universal fallback for `sans-serif`)
- [ ] Configure fontconfig to point to font directory
- [ ] Set FONTCONFIG_PATH/FONTCONFIG_FILE env vars for Chromium
- [ ] Verify with `ldd chrome | grep "not found"` for missing system libs
- [ ] After fixing: ALL text assertions should pass, not just some
