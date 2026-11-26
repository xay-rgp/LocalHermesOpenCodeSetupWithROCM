---
name: testing-qa
description: "Build unit, integration, E2E, fuzz, and CI test suites."
version: 1.0.0
author: Xay, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [testing, qa, pytest, integration, e2e, fuzzing, code-review, ci]
    related_skills: [test-driven-development, debugging-mastery, quality-assurance-policy, requesting-code-review]
---

# Testing and Quality Assurance

Designing reliable, fast, non-flaky test suites across unit, integration, end-to-end, regression, property-based, and code-review verification. Pair with `test-driven-development` for RED-GREEN-REFACTOR discipline.

## When to Use

- Designing a test strategy or adding coverage for a new feature, refactor, or bug fix
- Testing boundaries (databases, HTTP APIs, filesystems, CLI processes, UI flows) without brittle mocks
- Fixing flaky tests, writing property-based/fuzz tests, setting up CI gates, or performing thorough code reviews
- Don't use for: step-by-step TDD loop rules alone (load `test-driven-development`)

## Test Architecture Layers

| Layer | Scope | Speed | Use For | Avoid |
|---|---|---|---|---|
| **Unit** | Pure functions, domain rules, state machines | <10 ms | Invariants, edge cases, parsing, math, error paths | Heavy mock chains testing private methods |
| **Property / Fuzz** | Invariant holds for 100s–1000s generated inputs | 50 ms–5 s | Parsers, serializers, round-trips, algebraic laws, state transitions | UI layout checks |
| **Integration** | Module + real DB/FS/HTTP seam (tempdir, SQLite/test container) | 50 ms–2 s | SQL queries, migrations, serialization, permissions, subprocesses | Mocking the DB driver when testing SQL! |
| **Contract** | Producer/consumer schema & status code agreement | 10–100 ms | API endpoints, CLI JSON output, event payloads | Testing internal field ordering when irrelevant |
| **End-to-End (E2E)** | Full deployed/running binary or UI critical journeys | 2–30 s | Core user flows, startup/wiring, packaging | Exhaustive combinatorial edge cases |
| **Regression** | Minimal repro of every fixed bug | <100 ms | Guaranteeing fixed bugs never return | Deleting once bug is "old" |

## Core QA Rules

1. **Test observable behavior, never private implementation.** Refactoring internals without changing external contracts should break ZERO tests.
2. **Prefer real collaborators and in-memory fakes over mocks.** Mocks encode call-order assumptions and silently diverge from real APIs. Use real temp directories (`tmp_path`), real SQLite/test DBs, or a tiny fake implementation of a narrow `Protocol`/trait.
3. **Every test must be 100% isolated and deterministic.** Never depend on wall-clock `time.time()`, unseeded RNG, hardcoded TCP ports (bind port `0`!), shared global state, or test execution order.
4. **Always test boundaries and failure paths.** Happy path is necessary but never sufficient: test empty inputs, max sizes, Unicode/special chars, null/missing fields, permission errors, timeouts, duplicate submissions, and concurrent calls.
5. **Code review verifies invariants, not just style.** Automate formatting/linting; spend review effort on correctness, error propagation, concurrency safety, resource cleanup, security boundaries, and test quality.

## Deep References

Load on demand with `skill_view("testing-qa", file_path="...")`:
- `references/testing-strategies-and-review.md` — Concrete patterns for `pytest` (fixtures, parametrize, `hypothesis`), Rust (`cargo test`, `proptest`), JS/TS (`vitest`), C++ (`gtest`/`ctest`), flaky-test elimination, CI pipelines, and a rigorous code-review checklist.

## Testing Procedure

1. **Map risk and seams first.** Identify pure core logic (unit + property tests), I/O seams (integration tests with real temp resources), and critical user paths (E2E smoke tests). Completion criterion: every critical invariant is mapped to the lowest test layer that truly exercises it.
2. **Write boundary & failure tests alongside happy paths.** Parameterize edge cases (`@pytest.mark.parametrize` / table-driven tests) rather than copy-pasting tests. Completion criterion: error paths, boundary inputs, and regression cases all have explicit assertions.
3. **Verify failure sensitivity.** Confirm each new test actually fails when the corresponding behavior is broken (or via TDD RED phase). Completion criterion: no tautological assertions (`assert True`, asserting on mock return values).
4. **Run full suite + linters + repeat check for concurrency tests.** Run `terminal` test commands and confirm zero skips/xfails introduced silently. Completion criterion: 100% pass rate with clean output and zero leftover temp files or orphan processes.

## Common Pitfalls

- **Mocking the thing you're testing:** Mocking `sqlite3.connect` to test a repository proves only that your mock returned what you told it to return; SQL syntax and constraint errors pass undetected.
- **`time.sleep()` synchronization in tests:** Slow AND flaky under CI CPU load. Synchronize with `asyncio.Event`, `threading.Barrier`, condition variables, or polling with a bounded deadline.
- **Asserting only "did not raise":** Always assert the concrete resulting state, return value, or persisted record.
- **Predicting or fabricating test results:** NEVER write "running X will produce OK" without executing it via `terminal` AFTER your final edit. Every edit—even a 1-character typo fix—invalidates prior runs and requires re-execution.
- **Hidden test order dependency:** Randomize order (`pytest-randomly` or `cargo test` parallel default) to expose leaked module globals or uncleaned files.
- **Testing coverage % as the goal:** 100% line coverage with weak assertions misses off-by-one and branch logic bugs. Measure branch coverage and think adversarially (mutation mindset: "if I flip `<` to `<=`, does a test fail?").

## Verification

- Run project test runner (`pytest -v`, `cargo test`, `npm test`, `ctest --output-on-failure`) via `terminal`.
- Verify zero warnings/errors, clean teardown (no leftover temp dirs or background processes), and repeatability across multiple runs for async/concurrent tests.
