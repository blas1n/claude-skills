---
name: python-asyncio-live-stack-trace
description: Drop-in py-spy alternative for macOS — in-process SIGUSR signal handlers that dump thread tracebacks and asyncio task stacks to a file when the service is hung but you can't restart it.
---

# Python Asyncio Live Stack Trace (no py-spy / no root)

Use when a Python async service hangs in production-like conditions and
you need to see *which await is parked* without restarting it. Built-in
debuggers (py-spy, gdb-py) need root on macOS — denied in many sandbox
configurations. This pattern works without any privilege escalation.

## When to reach for this

- Long-running async service is alive but stuck (CPU 0%, no progress).
- You don't have py-spy access (macOS without root, restricted sandbox).
- Restarting would lose the bug (race conditions, rare states).
- You want repeatable observability across reproductions.

## The four traps before it works

### Trap 1 — `signal.signal()` cannot reach asyncio

A signal handler registered via `signal.signal(SIGUSR2, handler)` runs
in the signal-delivery context. From there, `asyncio.get_running_loop()`
raises `RuntimeError`, and `task.print_stack()` is unsafe across an
async boundary you don't own. The dump silently produces nothing.

**Fix**: register asyncio-aware handlers via `loop.add_signal_handler()`
*from inside the running loop*. The callback then runs as a regular
coroutine task — `all_tasks()` and `print_stack()` work normally.

```python
def _install_asyncio_signal(loop):
    def _dump():
        for task in asyncio.all_tasks(loop):
            task.print_stack(file=dump_fp)
    loop.add_signal_handler(signal.SIGUSR2, _dump)

# in lifespan startup:
_install_asyncio_signal(asyncio.get_running_loop())
```

For OS-level thread tracebacks (covers the GIL-blocked thread, native
hangs), use `faulthandler.register()` — that one IS signal-safe:

```python
faulthandler.register(signal.SIGUSR1, file=dump_fp, all_threads=True, chain=False)
```

### Trap 2 — backend stderr is unreachable

uvicorn / FastAPI typically writes to a foreground terminal you can't
SSH into. `faulthandler.register(file=sys.stderr)` is useless if you
can't read that stderr.

**Fix**: open a known file path at startup and write the dumps there.

```python
_dump_fp = open(os.getenv("APP_TRACE_DUMP_PATH", "/tmp/app-trace.log"),
                "a", buffering=1, encoding="utf-8")
faulthandler.register(signal.SIGUSR1, file=_dump_fp, all_threads=True, chain=False)
```

### Trap 3 — `rm /tmp/app-trace.log` orphans the open fd

If you `rm` (or even `touch -c` recreating the inode) the dump file
*after* the backend opened it, the process keeps writing to the
deleted-inode file. `ls -la /tmp/app-trace.log` shows 0 bytes — but
`lsof -p <pid> | grep trace` shows the orphaned fd has 2794 bytes.

```text
# Visible file (touched after rm):
-rw-r--r--  blasin  wheel  0 Apr 25 19:07 /tmp/app-trace.log
# What lsof shows for the worker:
python  85033  blasin  18w  REG  1,15  2794  21085813  /private/tmp/app-trace.log
                                              ↑ orphaned inode, not the visible one
```

**Fix**: don't `rm` after the process opened it. Either:

- Truncate in place: `: > /tmp/app-trace.log` (keeps inode).
- Or trigger a process reload so the process re-opens the visible file.

### Trap 4 — uvicorn `--reload` worker is not the supervisor

`uvicorn ... --reload` runs a supervisor process; the actual app + event
loop runs in a `multiprocessing.spawn` child. Signaling the supervisor
does nothing visible.

**Fix**: find the worker via `pgrep -P <supervisor_pid>` (filtering out
the multiprocessing helper):

```bash
ps -ef | grep "uvicorn.*--reload" | grep -v grep        # find supervisor
pgrep -P <supervisor>                                    # → worker pids
# pick the one whose elapsed time matches the latest reload
ps -p <candidate> -o pid,etime,command
```

The worker also owns the listening socket — confirm via:
`lsof -nP -p <pid> | grep LISTEN`.

## Complete recipe

```python
# main.py
import asyncio
import faulthandler
import os
import signal
from contextlib import asynccontextmanager

_TRACE_DUMP_PATH = os.getenv("APP_TRACE_DUMP_PATH", "/tmp/app-trace.log")
_trace_dump_fp = None


def _install_thread_traceback_signal():
    global _trace_dump_fp
    _trace_dump_fp = open(_TRACE_DUMP_PATH, "a", buffering=1, encoding="utf-8")
    faulthandler.register(signal.SIGUSR1, file=_trace_dump_fp,
                          all_threads=True, chain=False)


def _install_asyncio_signal(loop):
    import datetime as _dt

    def _dump():
        if _trace_dump_fp is None:
            return
        tasks = asyncio.all_tasks(loop)
        ts = _dt.datetime.now().isoformat(timespec="seconds")
        _trace_dump_fp.write(f"\n===== {ts} asyncio tasks: {len(tasks)} =====\n")
        for task in tasks:
            _trace_dump_fp.write(f"\n[{task.get_name()}] state={task._state}\n")
            try:
                task.print_stack(file=_trace_dump_fp)
            except Exception as exc:
                _trace_dump_fp.write(f"  print_stack failed: {exc}\n")
        _trace_dump_fp.write("===== end asyncio tasks =====\n\n")
        _trace_dump_fp.flush()

    loop.add_signal_handler(signal.SIGUSR2, _dump)


@asynccontextmanager
async def lifespan(app):
    _install_thread_traceback_signal()
    _install_asyncio_signal(asyncio.get_running_loop())
    yield
```

## How to use during a hang

```bash
# 1. find worker
WORKER=$(pgrep -P "$(pgrep -f 'uvicorn.*--reload' | head -1)" \
         | xargs -I{} sh -c 'ps -p {} -o pid=,etime= 2>/dev/null' \
         | sort -k2 | tail -1 | awk '{print $1}')

# 2. signal both
kill -USR2 "$WORKER"   # asyncio task stacks
kill -USR1 "$WORKER"   # OS thread tracebacks

# 3. read
tail -f /tmp/app-trace.log
```

The asyncio dump is what you almost always want first: it shows every
`Task pending` with its `running at <file>:<line>` and the inner-most
`await`. That points directly at the hang location.

## What the output looks like

```text
[Task-4385] state=PENDING
Stack for <Task pending name='Task-4385'
  coro=<_dispatch_background() running at .../dispatcher.py:238>
  wait_for=<Future pending cb=[Task.task_wakeup()]>>:
  File ".../dispatcher.py", line 238, in _dispatch_background
    result = await adapter.execute(

[Task-5898] state=PENDING
Stack for <Task pending name='Task-5898'
  coro=<acompletion() running at .../litellm/utils.py:1861>
  cb=[_release_waiter(<Future pending cb=[Task.task_wakeup()]>)()
      at .../asyncio/tasks.py:431]>:
  ...
```

Two signals worth knowing:

- `wait_for=<Future pending ...>` — task is parked on a low-level future
  (selector, lock, condition). Common at "healthy idle" points like
  `selector.select` or `asyncio.Queue.get`.
- `cb=[_release_waiter(...)]` — task is wrapped in `asyncio.wait_for`.
  If you see this on the suspicious task, the timeout backstop is
  active and the hang has a defined upper bound.

## Pairs well with

- Per-iteration / per-tool structured logs around the hot path so you
  can bracket *which* iteration parked. Without those, the stack tells
  you "where in the code", but not "for which input".
- A wall-clock budget (`asyncio.get_event_loop().time() - deadline`)
  inside the suspicious loop, so even unmonitored hangs eventually
  break out instead of accumulating forever.
