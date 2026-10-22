---
name: multiprocessing-pool-cannot-pickle-importlib-loaded-functions
description: A script that uses multiprocessing.Pool works when run directly, but breaks with "PicklingError: Can't pickle <function run>: it's not the same object as discover.run" once another script loads it via importlib.util.spec_from_file_location and calls its main(). Run it as a subprocess instead (or make it a real importable package). Triggers - research/helper scripts that are not a package, loading a sibling .py with importlib, a verify/rebuild wrapper calling another script's main(), Pool.imap with a module-level worker, macOS spawn start method.
---

# Pool workers from an importlib-loaded module do not pickle

## Symptom
`discover.py` (uses `Pool(8).imap(run, jobs)`) runs fine as `python discover.py ...`.
A wrapper `verify.py` loads it with `importlib.util.spec_from_file_location("discover", path)` and calls
`discover.main(...)` →
`_pickle.PicklingError: Can't pickle <function run at 0x...>: it's not the same object as discover.run`.

## Why
Pickle sends functions by reference: `module.__qualname__`. The module loaded by spec is not registered in
`sys.modules` under that name (and with spawn the child re-imports by name), so the lookup `discover.run`
fails or finds a different object. Running directly works because the worker lives in `__main__`, which
the spawn child re-runs.

## Fix (pick one)
- **Run the script as a subprocess** from the wrapper: `subprocess.run([sys.executable, str(HERE / "discover.py"), *args], check=True)` (no `shell=True`). Simplest for research scripts; also isolates state.
- Make the scripts a real package (`__init__.py`, import by dotted path) so `module.run` resolves in children.
- Register before use: `sys.modules[name] = module` before `exec_module` — works for fork, fragile for spawn; avoid.

## Check
Run the wrapper path once end-to-end (not just the script directly) before relying on it — the direct run never exercises the pickling path.
