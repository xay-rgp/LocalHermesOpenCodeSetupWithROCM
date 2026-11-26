---
name: polyglot-programming
description: "Master TypeScript, JavaScript, SQL, Bash, Fish, and async."
version: 1.0.0
author: Xay, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [typescript, javascript, sql, bash, fish, gdscript, concurrency, async]
    related_skills: [python-development, rust-development, cpp-c-development, godot-development, linux-development]
---

# Polyglot Programming

Cross-language mastery for TypeScript, JavaScript, SQL, Bash, Fish, and shared paradigms (memory models, concurrency, async I/O, structured error handling). Use language-specific sibling skills for deep Python, Rust, C/C++, or Godot 4 work.

## When to Use

- Writing or reviewing TypeScript/JavaScript (Node.js, browser, Bun, Deno), SQL queries/schemas, or Bash/Fish shell scripts
- Designing cross-language async workflows, cancellation, retry/timeout policies, or polyglot integrations
- Choosing the right concurrency model (event loop, threads, actors, processes, SQL transactions) for a problem
- Don't use for: deep Python (`python-development`), Rust (`rust-development`), C/C++ (`cpp-c-development`), or Godot 4 3D (`godot-development`)

## Core Cross-Language Principles

1. **Match the concurrency primitive to the workload:**
   - High-fanout I/O → single-threaded event loop (`asyncio`, Node/TS, Tokio) with bounded concurrency.
   - CPU-bound parallelism → OS threads/work-stealing pools (Rust Rayon, C++ thread pool, Python `ProcessPoolExecutor`, Node `worker_threads`).
   - Shared mutable state across workers → prefer immutable messages/channels or ACID database transactions over fine-grained mutex webs.
2. **Propagate cancellation and deadlines end-to-end.** Every network call, DB query, and subprocess needs an explicit timeout and cancellation token (`AbortSignal`, `context.Context`, `asyncio.timeout`, `tokio::time::timeout`).
3. **Validate at trust boundaries, type internally.** Parse untrusted JSON/SQL/env input once at the boundary (Zod/Valibot in TS, Pydantic in Python, `serde` in Rust), then pass strongly typed domain values internally.
4. **Never interpolate untrusted data into code.** Use parameterized SQL queries (`$1`/`?`), array-form `execFile`/`subprocess.run([...])` without `shell=True`, and quoted Bash variables (`"$var"`).

## Language Quick Reference

| Language | Strict Mode / Safety Baseline | Primary Async / Error Idiom |
|---|---|---|
| TypeScript | `"strict": true`, `"noUncheckedIndexedAccess": true`, no `any` | `async/await` + `AbortSignal` + discriminated `Result<T, E>` |
| JavaScript | `"use strict"` / ESM, `Object.freeze`, `Map`/`Set` for dynamic keys | `Promise.allSettled`, `try/catch` with `Error(..., { cause })` |
| SQL | Explicit column lists, parameterized queries, `EXPLAIN (ANALYZE, BUFFERS)` | Explicit `BEGIN ... COMMIT`, `SELECT ... FOR UPDATE`, `ON CONFLICT` |
| Bash | `set -Eeuo pipefail`, `IFS=$'\n\t'`, quote every `"$var"`, `shellcheck` | `trap cleanup EXIT`, arrays for argv, `mktemp` |
| Fish | `set -l` local vars, `status` checks, `string` builtin, no word-splitting | `begin; ...; end`, `functions`, `--on-event` handlers |

## Deep References

Load on demand with `skill_view("polyglot-programming", file_path="...")`:
- `references/js-ts-mastery.md` — Event loop (macrotasks vs microtasks), closures & memory leaks, TypeScript strict typing, discriminated unions, conditional/mapped types, `satisfies`, `AbortController`, ESM pitfalls.
- `references/sql-bash-fish-gdscript.md` — SQL CTEs, window functions, ACID isolation anomalies, indexing & `EXPLAIN ANALYZE`; Bash strict mode, arrays, traps, process substitution; Fish scoping, lists, functions; GDScript 4 typing summary.

## Implementation Procedure

1. **Turn on strict verification immediately.** TypeScript: `tsc --noEmit`; Bash: `shellcheck`; SQL: run `EXPLAIN ANALYZE` on realistic row counts; Fish: `fish -n script.fish`. Completion criterion: zero compiler/syntax/static-analysis errors.
2. **Enforce boundary safety.** Parameterize all SQL, validate external payloads into typed schemas, quote all shell expansions, and bound retries with exponential backoff + jitter. Completion criterion: fuzz/malformed inputs fail with structured errors rather than crashes or injections.
3. **Verify edge cases and failure modes.** Test timeouts, partial batch failures, SQL unique-constraint races, filenames with spaces/newlines in shell, and empty collections. Completion criterion: automated tests cover both happy path and failure recovery.

## Common Pitfalls

- **JS/TS `Promise.all` fail-fast leaks:** Rejects on first error while sibling promises keep running silently. Cancel siblings with `AbortController` or collect all outcomes with `Promise.allSettled`.
- **JS/TS `==` and `typeof null === "object"`:** Always use `===`/`!==` and explicit `val !== null && typeof val === "object"`.
- **TS `as Foo` casts:** Type assertions silence the compiler without runtime checks. Use type guards (`x is Foo`) or runtime validators (`zod`).
- **SQL `NULL` three-valued logic:** `col != 'x'` drops `NULL` rows! Use `IS DISTINCT FROM` or `col IS NULL OR col != 'x'`. Also `NOT IN (SELECT ...)` returns 0 rows if the subquery contains any `NULL` — use `NOT EXISTS`.
- **SQL N+1 queries:** Querying inside a loop destroys latency. Batch with `JOIN`, `ANY($1)`, or CTEs.
- **Bash unquoted expansions and `local x=$(cmd)`:** Unquoted `$var` breaks on spaces/globs. Also `local x=$(failing_cmd)` masks the exit status of `failing_cmd` because `local` returns 0! Declare `local x` on one line, then `x=$(failing_cmd)` on the next.
- **Fish vs Bash syntax confusion:** Fish does NOT use `$(...)` in older versions (3.4+ supports `$(cmd)`, classic is `(cmd)`), does NOT use `export A=B` (`set -gx A B`), and `$status` replaces `$?`.

## Verification

- TypeScript: `terminal(command="npx tsc --noEmit")`
- Bash: `terminal(command="bash -n script.sh && shellcheck script.sh")`
- Fish: `terminal(command="fish -n script.fish")`
- SQL: inspect query plan with `EXPLAIN (ANALYZE, BUFFERS)` and verify index scans instead of unexpected sequential scans on large tables.
