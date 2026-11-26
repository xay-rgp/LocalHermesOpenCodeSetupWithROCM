---
name: performance-profiling
description: "Profile CPU, memory, SQLite, and async bottlenecks in code."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [profiling, performance, cprofile, tracemalloc, optimization, big-o, sqlite, asyncio]
    related_skills: [debugging-mastery, python-development, rust-development, algorithms-cs]
---

# Performance Profiling & Bottleneck Elimination

Quantitative CPU, memory (`tracemalloc`), database query-plan, and concurrency profiling to isolate and eliminate latency and memory bottlenecks without changing observable behavior.

## When to Use

- Diagnosing slow functions, timeouts, quadratic $O(N^2)$ scaling blowups, or high CPU utilization
- Tracking down monotonically growing memory allocations (`tracemalloc`) or unbounded cache retention
- Optimizing N+1 database/SQLite query loops, missing indexes, or sequential I/O stalls
- Proving before-vs-after speedup factors and memory bounds with deterministic measurements
- Don't use for: premature micro-optimizations when no latency, throughput, or memory budget is violated

## Quantitative Profiling Rules

1. **Measure baseline before touching code.** Never guess the hotspot. Run `scripts/profile_harness.py` via `terminal` to record baseline wall-clock time (`elapsed_ms`), top `tottime`/`cumtime` frames, and peak memory (`peak_memory_kib`).
2. **Distinguish `tottime` (exclusive) vs `cumtime` (inclusive).**
   - High `tottime`: the loop, regex, or data-structure scan inside *that exact function* is burning CPU.
   - High `cumtime` with low `tottime`: the function is waiting on callees (e.g., N+1 database queries, repeated subprocess/file I/O, or deep recursion).
3. **Preserve 100% output equivalence.** Capture or test exact functional outputs before optimizing. An optimization that changes edge-case results or sort order is a bug.
4. **Target algorithmic and I/O complexity first.**
   - Replace $O(N \times M)$ nested list lookups (`item in list`) with $O(1)$ `set`/`dict` hash lookups.
   - Hoist `re.compile()`, schema parsing, and connection setup outside loops.
   - Replace per-item SQL queries (N+1) with a single indexed batch query + single transaction (`with conn:` + `executemany`).
   - Bound or clear class/global caches and history buffers (`collections.deque(maxlen=...)`) so repeated invocations do not leak RAM.

## Execution Workflow

1. **Run Baseline Profile:**
   Profile the target workload or benchmark entrypoint using the bundled profiler script:
   ```bash
   python3 ~/.hermes/skills/software-development/performance-profiling/scripts/profile_harness.py \
     --workdir /path/to/repo \
     --target "module_name:benchmark_fn" \
     --project-only \
     --output /path/to/repo/profile_before.json
   ```
2. **Analyze Top Hotspots & Memory Sites:**
   Inspect `top_tottime`, `top_cumtime`, and `top_allocations` in the profiler report to identify the top 1–3 root causes responsible for >80% of runtime or memory growth.
3. **Apply Targeted Algorithmic / I/O Fixes:**
   Refactor only the measured bottlenecks while keeping public signatures and return types identical.
4. **Verify Speedup & Correctness:**
   Re-run `profile_harness.py` with `--compare /path/to/repo/profile_before.json` and run `verify_gate.py` to confirm both the speedup target and full test suite pass:
   ```bash
   python3 ~/.hermes/skills/software-development/performance-profiling/scripts/profile_harness.py \
     --workdir /path/to/repo \
     --target "module_name:benchmark_fn" \
     --project-only \
     --compare /path/to/repo/profile_before.json \
     --output /path/to/repo/profile_after.json
   ```

## Bundled Scripts & Deep References

- `scripts/profile_harness.py` — Zero-dependency `cProfile` + `tracemalloc` + wall-clock profiler with `--project-only` frame filtering, memory-leak delta tracking across iterations (`--leak-iterations`), and `--compare` before/after speedup calculation.
- `references/profiling-and-complexity-fixes.md` — Load with `skill_view("performance-profiling", file_path="references/profiling-and-complexity-fixes.md")` for concrete patterns on eliminating $O(N^2)$ loops, SQLite `EXPLAIN QUERY PLAN` & batching, `asyncio` concurrency fan-out, and `tracemalloc` leak remediation.

## Common Pitfalls

- **Optimizing unprofiled code:** Rewriting cold setup functions saves 0.1 ms while an N+1 query or nested list scan inside a 5,000-iteration loop burns 2,000 ms.
- **Class-level or module-level mutable lists accumulating call history:** Appending to a class attribute (`_AUDIT_LOG = []`) across instance calls leaks memory monotonically. Use instance-scoped state or a bounded `collections.deque(maxlen=N)`.
- **Uncommitted or per-row auto-commit SQLite inserts:** Executing 3,000 individual `conn.execute("INSERT ...")` statements with `conn.commit()` inside the loop forces 3,000 disk/journal syncs. Wrap batch writes in a single `with conn:` transaction with `conn.executemany(...)` and index lookup columns (`CREATE INDEX IF NOT EXISTS ...`).
- **Breaking deterministic ordering when switching `list` to `set`:** Use a `set` for $O(1)$ membership testing (`if x in allowed_set:`), or preserve insertion order via `dict.fromkeys(...)`.

## Verification

- Confirm `profile_harness.py --compare profile_before.json` shows the required speedup factor and non-growing memory delta across iterations.
- Run `verify_gate.py` with the project's test suite and confirm `"status": "PASS"`.
