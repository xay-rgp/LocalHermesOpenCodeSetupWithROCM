---
name: python-development
description: "Write, type, optimize, and debug production Python code."
version: 1.0.0
author: Xay, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [python, typing, asyncio, concurrency, memory, packaging]
    related_skills: [debugging-mastery, testing-qa, software-architecture, polyglot-programming]
---

# Python Development

Production Python engineering across typing, data models, asyncio concurrency, memory management, error handling, and packaging.

## When to Use

- Designing, writing, refactoring, typing, or profiling Python 3.10+ codebases
- Building `asyncio` services, concurrent pipelines, or CPU-bound multiprocessing workers
- Investigating Python memory leaks, GIL contention, subtle mutable-state bugs, or packaging issues
- Don't use for: trivial one-line shell math or non-Python codebases

## Core Discipline

1. **Inspect before editing.** Read existing code with `read_file` and locate callers with `search_files` before changing signatures or data flow.
2. **Type all public boundaries.** Annotate parameters and return types using `collections.abc` (`Sequence`, `Mapping`, `Iterable`) for inputs and concrete types (`list`, `dict`) for outputs. Use `Protocol` for structural interfaces instead of deep inheritance.
3. **Fail explicitly with domain errors.** Define a module exception hierarchy (`class AppError(Exception)`) and preserve causality with `raise DomainError("...") from exc`. Never write bare `except:` or swallow exceptions silently.
4. **Make invalid states unrepresentable.** Use `@dataclass(frozen=True, slots=True)`, `Enum`, `NewType`, and `Literal` for domain values.
5. **Respect ownership of resources.** Acquire files, sockets, locks, and DB sessions exclusively through `with` / `async with` context managers (`contextlib.ExitStack` / `AsyncExitStack` for dynamic sets).

## Quick Reference

| Concern | Default Tool / Idiom | Avoid |
|---|---|---|
| Data records | `@dataclass(frozen=True, slots=True)` | Unstructured dicts passed across modules |
| Interfaces | `typing.Protocol` + `mypy`/`pyright` | Deep ABC inheritance trees |
| Async fan-out | `asyncio.TaskGroup()` + `asyncio.Semaphore` | Fire-and-forget `create_task()` (GC'd tasks!) |
| CPU-bound work | `ProcessPoolExecutor` / C/Rust extension | `threading` under standard GIL |
| Blocking I/O in async | `await asyncio.to_thread(fn, ...)` | Calling `requests.get()` / `time.sleep()` inside `async def` |
| Paths & tempfiles | `pathlib.Path`, `tempfile.TemporaryDirectory` | Manual string concat or hardcoded `/tmp` |
| Packaging & deps | `pyproject.toml` + `uv`/`venv` + lockfile | Global `pip install` without pinned versions |

## Deep References

Load on demand with `skill_view("python-development", file_path="...")`:
- `references/typing-and-metaprogramming.md` — Generics, `Protocol`, `ParamSpec`, descriptors, `__slots__`, `__init_subclass__`, metaclasses, immutability patterns.
- `references/async-concurrency-memory.md` — `asyncio` event loop internals, cancellation safety, backpressure, GIL & multiprocessing, `tracemalloc`, GC cycles, weakrefs, profiling.

## Implementation Procedure

1. **Define types and invariants first.** Model inputs, outputs, and error classes before implementing logic. Completion criterion: static checker (`mypy` or `pyright` if installed) reports 0 errors on modified files.
2. **Keep I/O at the edges.** Separate pure domain logic from filesystem, HTTP, and database calls so core logic is testable without mocks. Completion criterion: core functions run in-memory with zero network/disk dependencies.
3. **Guard concurrency explicitly.** Bound concurrency with `asyncio.Semaphore` or queue `maxsize`, hold strong references to background tasks, and never suppress `asyncio.CancelledError`. Completion criterion: every spawned task is awaited or cancelled cleanly on shutdown.
4. **Verify with tests and lint.** Run tests via `terminal(command="pytest -q")` and static checks (`ruff check`, `mypy`) when present. Completion criterion: all unit and regression tests pass with zero warnings introduced.

## Common Pitfalls

- **Mutable default arguments:** `def f(items=[])` shares one list across all calls. Always use `items: list[str] | None = None`.
- **Late-binding closures in loops:** `[lambda: i for i in range(3)]` all return `2`. Bind eagerly (`lambda i=i: i`) or use `functools.partial`.
- **Fire-and-forget `asyncio.create_task()`:** The event loop holds only a weak reference; tasks can be garbage-collected mid-execution. Store tasks in a `set` with `task.add_done_callback(tasks.discard)` or use `asyncio.TaskGroup`.
- **Blocking the event loop:** Synchronous `requests`, `sqlite3`, `time.sleep`, or heavy JSON/regex in `async def` freezes all coroutines. Offload with `asyncio.to_thread`.
- **Swallowing `CancelledError`:** In Python 3.8+, `CancelledError` inherits from `BaseException`, not `Exception`, but `except BaseException:` or `return` inside `finally:` silently swallows cancellation and hangs shutdown. Never put `return`/`break`/`continue` in a `finally:` block!
- **Skipping compile/test after small edits:** Always run `python3 -m py_compile <files>` and the test suite via `terminal` after the FINAL edit — never predict or fabricate passing output.
- **Unbounded caches (`@lru_cache(maxsize=None)` on methods):** Caching a bound method retains `self` forever, leaking every instance. Move `@lru_cache(maxsize=256)` to a module-level helper and delegate from the method! Similarly, store observers/hooks in `weakref.WeakSet` (never strong `list`), and record error summaries as formatted strings (`f"{type(exc).__name__}: {exc}"`) in a bounded `collections.deque(maxlen=...)` instead of storing raw `Exception` instances (which pin stack frames and locals via `__traceback__`).
- **Parameterized SQLite queries & atomic transactions:** Always use `?` placeholders (never f-strings) with `sqlite3`, wrap multi-statement writes in `with self._conn:` + a `threading.Lock`, and implement `__enter__`/`__exit__` calling `close()`.
- **Shadowing stdlib modules:** Naming a file `logging.py`, `json.py`, or `typing.py` breaks imports across the process.
- **Regex shell escaping trap:** Do not inline Python regexes containing `\$` in double-quoted bash `-c`; bash strips `\`. Write a `.py` file or use single quotes.
- **Validate JSON container types explicitly:** Never call `.items()` or subscript `json.loads(data)` without first checking `isinstance(raw, dict)` and `isinstance(entry, dict)`. Passing `"123"` or `"[...]"` to `.items()` raises `AttributeError`, bypassing `except (json.JSONDecodeError, KeyError, TypeError, ValueError)`.
- **Use `isinstance(x, int) and not isinstance(x, bool)` for integer validation:** In Python, `bool` subclasses `int`, so `isinstance(True, int)` is `True`.
- **Surgical `patch` over full-file rewrites:** When fixing a bug in one function, use `patch` on ONLY the broken lines. Rewriting an entire working file risks introducing new identifier typos in already-passing methods. Never work around a mid-generation typo by appending a second `*_fixed` method or helper—patch the broken line cleanly, pass exact file paths without backticks, run `python3 -m py_compile` and a smoke test covering every public method after the final edit, and never leave `# Fix this` comments behind.
- **`heapq.heapify()` mutates in-place and returns `None`:** Never write `h = heapq.heapify(items)` or `list(heapq.heapify(items))` (raises `TypeError: 'NoneType' object is not iterable`). Always write `heap = [...]; heapq.heapify(heap)`.
- **Always save files via `write_file`:** Never output a Python module only in a chat code block when asked to create a file — call `write_file` and verify with `python3 -m py_compile`.

## Verification

- Run `terminal(command="pytest -q")` and confirm all existing and new tests pass.
- Run `terminal(command="python3 -m py_compile <files>")` (and `ruff check` / `mypy` if available).
- For memory-sensitive code, verify steady RSS / `tracemalloc` snapshot delta across repeated iterations.

## Course 3 Senior Python Pitfalls (Verified)
- **`bool` Is a Subclass of `int`:** When validating numeric parameters (`int`, `float`, delays, timeouts, counts), ALWAYS reject booleans explicitly: `isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x)`.
