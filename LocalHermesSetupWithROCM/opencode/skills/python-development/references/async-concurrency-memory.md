# Python Async, Concurrency, and Memory Reference

## 1. `asyncio` Architecture & Structured Concurrency

`asyncio` is **cooperative single-threaded multitasking**: a coroutine only yields control at `await` points.

### Structured Concurrency with `asyncio.TaskGroup` (Python 3.11+)
Prefer `TaskGroup` over `asyncio.gather()`:
- Automatically cancels sibling tasks if one raises an exception.
- Guarantees no orphaned background tasks escape the scope.
- Raises `ExceptionGroup` (handle with `except* SpecificError as eg:`).

```python
import asyncio
from collections.abc import Iterable

async def fetch_all(urls: Iterable[str], limit: int = 10) -> list[str]:
    sem = asyncio.Semaphore(limit)
    results: dict[str, str] = {}

    async def worker(url: str) -> None:
        async with sem:
            async with asyncio.timeout(5.0):
                results[url] = await fetch_one(url)

    async with asyncio.TaskGroup() as tg:
        for url in urls:
            tg.create_task(worker(url))

    return [results[u] for u in urls]
```

### Cancellation Safety Rules
1. `asyncio.CancelledError` is a `BaseException`. If you catch it for cleanup, **always re-raise it** unless you are intentionally implementing a cancellation boundary (like `asyncio.timeout`).
2. Never put `return` or `break` inside a `finally:` block — it silently swallows pending `CancelledError` and other exceptions.
3. For critical cleanup that must run during cancellation, wrap only the tiny cleanup step in `asyncio.shield(...)` or make cleanup synchronous and fast.
4. Bound producer-consumer pipelines with `asyncio.Queue(maxsize=N)` so slow consumers exert backpressure instead of OOMing the process.

### Offloading Blocking Work
- Blocking I/O (`requests`, `sqlite3`, synchronous file reads): `await asyncio.to_thread(fn, *args)` (uses default ThreadPoolExecutor).
- CPU-heavy work (parsing huge payloads, crypto, compression, numeric loops): `loop.run_in_executor(process_pool, fn, *args)` because threads serialize on the GIL.
- Detect accidental blocking with `PYTHONASYNCIODEBUG=1` — Python logs warnings whenever a callback blocks the loop for >100ms (`loop.slow_callback_duration`).

## 2. Concurrency Selection Matrix

| Workload | Mechanism | Shared State | Caveat |
|---|---|---|---|
| 100–100k network sockets | `asyncio` | Single thread (still needs `asyncio.Lock` across `await`!) | Any blocking call stalls all tasks |
| Blocking C/I/O libraries | `ThreadPoolExecutor` | Shared memory + `threading.Lock` | Race conditions; GIL blocks pure-Python CPU |
| Pure Python CPU-bound | `ProcessPoolExecutor` / Cython / PyO3 Rust | IPC / `multiprocessing.shared_memory` | Pickling overhead; use `spawn` start method on Linux if threads/CUDA/ROCm exist (`fork` deadlocks multithreaded processes!) |

### Critical Linux `fork` Hazard
Never use `multiprocessing` default `fork` after threads, OpenSSL, SQLite, or GPU runtimes (CUDA/ROCm) have been initialized — child inherits locked mutexes held by vanished threads and deadlocks. Always set `multiprocessing.get_context("spawn")`.

## 3. Memory Management, Leaks, and Profiling

Python combines **reference counting** (immediate deallocation when refcount hits 0) with a **generational cyclic garbage collector** (collects reference cycles among container objects).

### Top Real-World Python Memory Leaks
1. **Unbounded caches / module-level dicts:** `@lru_cache(maxsize=None)` on methods retains `self` forever. Use `maxsize=1024` or `weakref.WeakKeyDictionary`.
2. **Forgotten callbacks / signal listeners / observer lists:** Use `weakref.WeakSet` or explicit unregister in `finally`.
3. **Retained tracebacks (`exc.__traceback__`):** Storing exception objects in long-lived lists pins every local variable in every stack frame of the traceback. Format to string (`traceback.format_exc()`) instead of keeping the `Exception` instance.
4. **Reference cycles with custom `__del__` or C extensions:** Inspect with `gc.garbage` and break cycles with `weakref.ref`.
5. **Memory fragmentation (glibc arenas / pymalloc):** Freed Python objects stay in pymalloc pools or glibc heaps; RSS may not shrink immediately. Check if growth is bounded (plateau = fragmentation) vs unbounded linear growth (true leak).

### Pinpointing Leaks with `tracemalloc`
```python
import tracemalloc

tracemalloc.start(10)  # capture 10-frame tracebacks
snap1 = tracemalloc.take_snapshot()
run_suspected_workload()
snap2 = tracemalloc.take_snapshot()

for stat in snap2.compare_to(snap1, "lineno")[:10]:
    print(stat)
```

### CPU & Async Profiling Commands
- Sampling profiler (low overhead, production-safe): `py-spy top --pid <PID>` or `py-spy record -o flame.svg -- python app.py`
- Deterministic stdlib profiler: `python3 -m cProfile -s cumtime app.py | head -n 40`
- Memory profiler for native + Python allocations: `memray run app.py && memray flamegraph memray-*.bin`
