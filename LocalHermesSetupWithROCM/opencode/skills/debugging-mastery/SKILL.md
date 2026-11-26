---
name: debugging-mastery
description: "Diagnose stack traces, leaks, races, and perf bottlenecks."
version: 1.0.0
author: Xay, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [debugging, sanitizers, profiling, memory-leaks, race-conditions, bisect]
    related_skills: [systematic-debugging, testing-qa, cpp-c-development, python-development, rust-development]
---

# Debugging Mastery

Technical diagnostic techniques for stack traces, compiler/linker errors, memory leaks, race conditions, regression bugs, and performance bottlenecks. Pair with `systematic-debugging` for the 4-phase root-cause investigation process.

## When to Use

- Interpreting deep stack traces, segfaults, compiler/template/borrow-checker errors, or linker failures
- Tracking down memory leaks, use-after-free, buffer overflows, or RSS growth
- Reproducing and diagnosing race conditions, deadlocks, flaky tests, or heisenbugs
- Automating regression hunting (`git bisect`) or isolating CPU/I/O/lock performance bottlenecks
- Don't use for: general workflow discipline alone (load `systematic-debugging` for the 4-phase process)

## Diagnostic Decision Matrix

| Failure Class | First Instrumentation Tool | Root-Cause Signal to Look For |
|---|---|---|
| Crash / exception | Full stack trace + local variables (`pdb`, `gdb`, `lldb`, `RUST_BACKTRACE=full`) | First frame in **your** code + exact offending input/state |
| C/C++ memory error | `-fsanitize=address,undefined -fno-omit-frame-pointer` or `valgrind` | Allocation stack vs free stack vs invalid access stack |
| Python memory leak | `tracemalloc` snapshot diff / `memray` | Monotonically growing allocation site across N iterations |
| Rust `unsafe` UB | `cargo +nightly miri test` | Stacked/Tree Borrows violation, uninit read, dangling ptr |
| Data race / deadlock | `-fsanitize=thread` (C/C++), `gdb thread apply all bt`, `py-spy dump` | Unsynchronized shared write or cyclic lock acquisition (A→B vs B→A) |
| Regression bug | `git bisect run <repro_script>` | Exact first bad commit + minimal diff |
| CPU / latency bottleneck | `perf record -g`, `py-spy record`, `EXPLAIN (ANALYZE, BUFFERS)` | Inclusive vs exclusive hot frame, lock wait, or seq scan |
| Syscall / env / I/O stall | `strace -ff -tt -T -e trace=file,network,process` | Failing `ENOENT`/`EACCES`, hanging `futex`/`poll`, repeated `openat` |

## Deep References

Load on demand with `skill_view("debugging-mastery", file_path="...")`:
- `references/memory-races-and-profilers.md` — Reading ASan/UBSan/TSan/Valgrind reports, compiler/linker error decoding, deadlock & race reproduction harnesses, automated `git bisect run`, `gdb`/`pdb`/`strace`/`perf` command recipes.

## Investigation Procedure

1. **Read the complete error from bottom to top (and top to bottom).**
   - Python: read bottom line (exception type + message), then walk up to the first frame in project code; always inspect `__cause__` / `__context__` chained tracebacks.
   - C/C++/Rust compiler: **fix the FIRST error first** — downstream errors are usually cascading fallout from broken syntax or types.
   - Linker (`undefined reference` / `multiple definition`): check missing library order (in GCC/ld, dependents come BEFORE dependencies: `main.o -lfoo`), `extern "C"` name mangling mismatch, or non-`inline` definitions in headers.
   Completion criterion: exact failing symbol, file, line, and error class are identified.
2. **Build a fast deterministic reproducer.** Shrink inputs and isolate the bug into a single command or test. For timing/race bugs, stress-loop (`for i in $(seq 1 100); do ... || break; done`) or run under TSan/stress-concurrency (`loom` in Rust, thread barriers in Python/C++). Completion criterion: failure reproduces reliably on demand.
3. **Inspect live state, not guesses.** Use a debugger (`gdb -batch -ex run -ex bt`, `python3 -m pdb`), sanitizers, or structured boundary logs rather than sprinkling speculative edits. Completion criterion: observed runtime values prove the broken invariant.
4. **Fix root cause and lock in a regression test.** Write a minimal test that fails before the fix and passes after, then run the full suite. Completion criterion: regression test passes and zero temporary debug artifacts remain.

## Common Pitfalls

- **Treating symptoms with `try/except: pass`, `sleep(0.5)`, or null-checks without knowing WHY it was null:** Hides corruption and moves failures downstream where they are 10x harder to debug.
- **Debugging optimized release binaries without symbols:** Inlining and dead-code elimination distort line numbers and hide locals. Reproduce with `-O1 -g -fno-omit-frame-pointer` (or `-O0 -g` if not optimization-dependent; if it disappears at `-O0`, suspect UB or data race!).
- **Confusing memory fragmentation with a memory leak:** Measure across 10x iterations; a real leak grows linearly without bound, whereas arena pooling plateaus.
- **Ignoring `stderr` or truncated logs:** Always inspect exit codes and full `stderr` before concluding a tool "silently failed."
- **Combining ASan and TSan in one binary:** They are mutually incompatible; build separate sanitizer targets.
- **Claiming `[VERIFIED]` after an uncompiled edit or budget wrap-up:** If you edited a file and did not run the compiler/test command afterward (or a tool call failed), explicitly state **UNVERIFIED** and report the last real exit code. Never fabricate expected output.

## Verification

- Confirm the exact failing reproducer fails BEFORE the patch and passes AFTER the patch.
- Re-run with sanitizers / race detector / profiler active to confirm the underlying defect (not just the symptom) is gone.
- Run the full test suite via `terminal` to confirm zero regressions.
