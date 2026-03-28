---
name: remotion-cli-integration
description: "Remotion CLI Integration (Python Subprocess) — patterns and pitfalls for video rendering"
version: 1.0.0
---

# Remotion CLI Integration (Python Subprocess)

Patterns and pitfalls when calling Remotion CLI from Python via subprocess for video rendering.

## When to Apply

- Calling Remotion CLI from a Python backend via subprocess
- Passing assets to Remotion compositions using `staticFile()`
- Running Remotion in headless Chrome environments (Docker/DevContainer)

---

## 1. Asset Delivery: `staticFile()` Only

### Pitfall: `file://` URLs Do Not Work

Remotion renderer only supports **`http://`, `https://`, and `staticFile()`** as asset sources.
The `file://` protocol is silently ignored or causes errors during rendering.

```tsx
// WRONG - file:// URLs fail at render time
<Audio src={`file://${props.audio_path}`} />
<Img src={`file://${props.image_path}`} />

// CORRECT - use staticFile() with relative paths from public/
<Audio src={staticFile(props.audio_path)} />
<Img src={staticFile(props.image_path)} />
```

### `staticFile()` Resolution Rules

- `staticFile("audio.wav")` → `<remotion_project>/public/audio.wav`
- `staticFile("subdir/image.png")` → `<remotion_project>/public/subdir/image.png`
- **Absolute paths do not work**: `staticFile("/tmp/audio.wav")` → 404

---

## 2. Asset Staging Pattern

To pass assets from Python to Remotion, files must be **physically copied** into the Remotion project's `public/` directory.

### Pitfall: `--public-dir` Flag Does Not Exist in Remotion v4

```bash
# WRONG - this flag does not exist
npx remotion render src/index.ts MyComp out.mp4 --public-dir /tmp/my-assets

# CORRECT - place files directly in the project's public/ directory
```

### Pitfall: Symlinks Are Ignored During Bundling

Remotion copies `public/` into a webpack bundle (`/tmp/remotion-webpack-bundle-xxx/public/`) at render time.
**Symlinks are not followed** during this copy, leaving the bundle without the actual files.

```python
# WRONG - symlinks are ignored during webpack bundle copy
dest.symlink_to(src.resolve())

# CORRECT - use actual file copy
shutil.copy2(src, dest)
```

### Recommended Pattern: Per-Render Unique Subdirectory

```python
import os, time, shutil
from pathlib import Path

REMOTION_DIR = Path("/workspace/remotion")

# Unique ID per render to avoid collisions
render_id = f"_render_{os.getpid()}_{int(time.time())}"
public_dir = REMOTION_DIR / "public" / render_id
public_dir.mkdir(parents=True, exist_ok=True)

# Copy assets
shutil.copy2(audio_path, public_dir / "audio.wav")

# Pass relative paths (from public/) in props
props = {"audio_path": f"{render_id}/audio.wav"}

try:
    # render...
    pass
finally:
    # Always clean up after render
    shutil.rmtree(public_dir, ignore_errors=True)
```

---

## 3. Headless Chrome in Docker/DevContainer

Remotion uses Chromium internally. Docker environments may be missing required shared libraries.

### Required Packages (Debian/Ubuntu)

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxrandr2 libgbm1 libasound2 libpango-1.0-0 \
    libpangocairo-1.0-0 libcairo2 libxshmfence1
```

### Without sudo (existing container, ARM64 Debian trixie)

Extract .deb packages manually:

```bash
DEPS_DIR=~/.local/lib/chromium-deps
mkdir -p "$DEPS_DIR"
# Download .debs → dpkg-deb -x → extract to $DEPS_DIR
export LD_LIBRARY_PATH="$DEPS_DIR/usr/lib/aarch64-linux-gnu:$LD_LIBRARY_PATH"
```

Inject via Python environment:

```python
env = os.environ.copy()
chromium_libs = Path.home() / ".local/lib/chromium-deps/usr/lib/aarch64-linux-gnu"
if chromium_libs.exists():
    env["LD_LIBRARY_PATH"] = f"{chromium_libs}:{env.get('LD_LIBRARY_PATH', '')}"

proc = await asyncio.create_subprocess_exec(*cmd, env=env, cwd=str(REMOTION_DIR))
```

---

## 4. CLI Invocation Pattern

```python
cmd = [
    "npx", "remotion", "render",
    str(entry_point),      # e.g. "src/index.ts"
    composition_id,        # e.g. "KoreanShorts"
    str(output_path),      # e.g. "/tmp/output.mp4"
    "--props", str(props_json_path),  # JSON file path (avoids shell escaping)
    "--log", "error",      # suppress verbose output
]
```

### Always Pass Props via JSON File

```python
# WRONG - shell escaping issues with inline JSON
cmd += ["--props", json.dumps(props)]

# CORRECT - save to JSON file, pass file path
props_path = output_dir / "remotion_props.json"
props_path.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
cmd += ["--props", str(props_path)]
```

### Pitfall: Relative Paths Break When cwd Differs

Remotion CLI runs with `cwd=<remotion_project>/`. If props or output paths are relative to a different directory (e.g. the Python process cwd), they won't resolve correctly.

```python
# WRONG - relative path breaks because CLI cwd ≠ Python cwd
props_path = output_dir / "remotion_props.json"  # e.g. "outputs/videos/xxx/props.json"
cmd += ["--props", str(props_path)]  # Remotion looks for "remotion/outputs/videos/..."

# CORRECT - always resolve to absolute paths
props_path = (output_dir / "remotion_props.json").resolve()
output_mp4 = output_path.with_suffix(".mp4").resolve()
cmd += ["--props", str(props_path)]
```

---

## Key Lessons

| Assumption | Reality |
|------------|---------|
| `file://` URLs work for assets | Only `staticFile()` or `http(s)://` supported |
| `--public-dir` flag exists | Not available in Remotion v4 |
| Symlinks work for asset staging | Webpack bundler does not follow symlinks |
| Chromium works out of the box in Docker | Shared libraries must be manually installed |
| Relative paths work with `--props` | CLI resolves paths from its own cwd, not caller's |

**Verification order**: Check CLI flags (`--help`) → Small standalone render test → Python integration test
