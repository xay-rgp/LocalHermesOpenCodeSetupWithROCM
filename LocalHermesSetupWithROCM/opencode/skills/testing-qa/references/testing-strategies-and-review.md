# Testing Strategies, Flake Elimination, CI Gates, and Code Review

## 1. Concrete Idiomatic Test Patterns

### Python: `pytest`
Prefer explicit fixtures with `yield` teardown, `tmp_path`, `monkeypatch`, and parameterized edge cases:
```python
import pytest

@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))
    repo = SqliteOrderRepo(tmp_path / "test.db")
    repo.migrate()
    yield repo
    repo.close()

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("0.00", 0, id="zero"),
        pytest.param("19.99", 1999, id="standard"),
        pytest.param(" 42.5 ", 4250, id="whitespace"),
    ],
)
def test_parse_cents_valid(raw: str, expected: int) -> None:
    assert parse_cents(raw) == expected

def test_parse_cents_rejects_negative() -> None:
    with pytest.raises(ValueError, match="must be non-negative"):
        parse_cents("-1.00")

@pytest.mark.asyncio
async def test_fetch_times_out(fake_server) -> None:
    fake_server.set_delay(0.5)
    with pytest.raises(TimeoutError):
        await fetch_quote(fake_server.url, timeout=0.05)
```

### Python: `hypothesis` Property-Based Testing
Test algebraic invariants across 100s of auto-shrunk edge cases (empty strings, Unicode surrogates, `NaN`, extremes):
```python
from hypothesis import given, settings, strategies as st

# 1. Round-trip property
@given(st.dictionaries(st.text(max_size=20), st.integers(-10**9, 10**9)))
@settings(max_examples=200)
def test_codec_round_trip(payload: dict[str, int]) -> None:
    assert decode_frame(encode_frame(payload)) == payload

# 2. Algebraic invariant property (without reimplementing the algorithm)
@given(st.lists(st.integers(-1000, 1000), max_size=50))
def test_sort_invariants(xs: list[int]) -> None:
    out = custom_sort(xs)
    assert len(out) == len(xs)
    assert all(a <= b for a, b in zip(out, out[1:]))

# 3. Oracle / differential property (fast algorithm == simple brute-force reference)
@given(st.lists(st.integers(-1000, 1000), max_size=50))
def test_fast_dedup_matches_reference(xs: list[int]) -> None:
    assert fast_dedup_preserving_order(xs) == list(dict.fromkeys(xs))
```
When a failure is found, lock in the shrunk example as a permanent `@example(...)` regression test.

### Rust: `#[cfg(test)]`, Integration `tests/`, and `proptest`
```rust
// src/parser.rs — unit tests access private helpers inside the module
#[cfg(test)]
mod tests {
    use super::*;
    use proptest::prelude::*;

    #[test]
    fn rejects_empty_header() {
        assert!(matches!(parse_header(b""), Err(ParseError::Empty)));
    }

    proptest! {
        #[test]
        fn frame_roundtrip(bytes in prop::collection::vec(any::<u8>(), 0..256)) {
            let encoded = encode_frame(&bytes);
            prop_assert_eq!(decode_frame(&encoded).unwrap(), bytes);
        }
    }
}
// tests/api_integration.rs — compiled as an external crate: verifies public API + real TempDir
```
Run with `cargo test --all-targets`.

### TypeScript: `vitest`
```ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

describe("TokenExpiry", () => {
  let dir: string;
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T00:00:00Z"));
    dir = mkdtempSync(join(tmpdir(), "vitest-"));
  });
  afterEach(() => {
    vi.useRealTimers();
    rmSync(dir, { recursive: true, force: true });
  });

  it.each([
    { ttlMs: 1000, advanceMs: 999, valid: true },
    { ttlMs: 1000, advanceMs: 1000, valid: false },
  ])("expiry boundary ttl=$ttlMs advance=$advanceMs", ({ ttlMs, advanceMs, valid }) => {
    const tok = issueToken(ttlMs);
    vi.advanceTimersByTime(advanceMs);
    expect(isTokenValid(tok)).toBe(valid);
  });
});
```

### C++: `gtest` + `ctest`
```cpp
#include <gtest/gtest.h>
#include <filesystem>

class StoreTest : public ::testing::Test {
protected:
    std::filesystem::path dir;
    void SetUp() override {
        auto* info = ::testing::UnitTest::GetInstance()->current_test_info();
        dir = std::filesystem::temp_directory_path() / (std::string("gt_") + info->name());
        std::filesystem::create_directories(dir);
    }
    void TearDown() override { std::filesystem::remove_all(dir); }
};

TEST_F(StoreTest, RejectsNegativeCapacity) {
    EXPECT_THROW(RingBuffer(-1), std::invalid_argument);
}
// Build & run with sanitizers:
// ctest --test-dir build-asan --output-on-failure -j"$(nproc)"
```
Use `ASSERT_*` only when continuing the test would dereference null/UB; prefer `EXPECT_*` so all failed assertions in a test report together.

---

## 2. Test Doubles Hierarchy & Why Fakes Beat Over-Mocking

| Double | Purpose | Safe Use Case | Failure Mode When Abused |
|---|---|---|---|
| **Dummy** | Placeholder arg never read | Satisfying unused logger/tracer param | Minimal risk |
| **Stub** | Returns canned values | Simulating error status/timeout from HTTP port | Divergence from real API error payload |
| **Spy** | Records calls for inspection | Verifying an audit event or metric was emitted once | Asserting exact internal call counts that shouldn't matter |
| **Mock** | Pre-programmed expectation on calls/order | Narrow third-party webhook boundary with no sandbox | Couples tests to private call sequence; breaks on valid refactors |
| **Fake** | Working lightweight in-memory/SQLite implementation | `InMemoryRepo`, `FixedClock`, local loopback HTTP server | Fake subtly disagrees with real Postgres SQL behavior |

### Solving Fake Drift with a Shared Contract Suite
Run the **exact same contract test suite** against both your `FakeOrderRepo` and your real `PgOrderRepo`:
```python
@pytest.fixture(params=["fake", "postgres"])
def order_repo(request, pg_pool):
    if request.param == "fake":
        return InMemoryOrderRepo()
    return PgOrderRepo(pg_pool)

def test_duplicate_idempotency_key_raises_conflict(order_repo) -> None:
    order_repo.insert(Order(id="1", key="k1"))
    with pytest.raises(DuplicateKeyError):
        order_repo.insert(Order(id="2", key="k1"))
```
Result: unit tests using `InMemoryOrderRepo` run in microseconds AND stay behaviorally faithful to production SQL semantics.

---

## 3. Flaky Test Taxonomy & Deterministic Fixes

| Flake Cause | Symptom | Deterministic Fix |
|---|---|---|
| **Wall-clock time / DST** | Fails at midnight, month-end, or CI timezone != local | Inject `Clock` (`FixedClock(datetime(2026, 1, 1, tzinfo=UTC))`) or `vi.useFakeTimers()` |
| **Unseeded PRNG** | Random 1-in-50 failure | Inject `random.Random(42)` / seeded PRNG; log seed on failure |
| **Hardcoded ports / shared paths** | `Address already in use` or parallel worker collisions | Bind ephemeral port `0` (`sock.bind(("127.0.0.1", 0))`), use `tmp_path` / `mkdtemp`, per-worker DB schema (`pytest-xdist`) |
| **`sleep()` synchronization** | Passes locally, fails under slow CI CPU | Wait on `threading.Event.wait(timeout=2.0)`, `asyncio.Event`, `Barrier`, or bounded poll loop (`10ms` interval, `2s` deadline) |
| **Order / hash randomization** | Passes in isolation, fails in full suite | Run `pytest -p randomly` / `PYTHONHASHSEED=random` / `cargo test`; reset module globals in `yield` teardown; compare sorted outputs |
| **Leaked async tasks / FDs** | `Task was destroyed but it is pending!`, FD exhaustion | Structured concurrency (`asyncio.TaskGroup`), close clients in `finally`/`yield`, fail on `ResourceWarning` (`-W error::ResourceWarning`) |

---

## 4. CI Quality Gates

Design gates from fastest/cheapest to slowest/deepest:

```text
[PR Gate 1: <2 min] ─▶ [PR Gate 2: 2–10 min] ─▶ [Merge/Nightly Gate 3]
  fmt + lint + types      DB/FS integration        E2E critical journeys
  unit + property tests   ASan+UBSan & TSan        Schema forward+backward check
                          dep/secret CVE audit     Flake stress (--count=20 on changed tests)
```

- **Gate 1 (Fast PR Feedback):**
  ```bash
  ruff format --check . && ruff check . && mypy src/ && pytest -m "not integration" -q
  # Rust: cargo fmt --check && cargo clippy --all-targets -- -D warnings && cargo test --lib
  # TS:   npx tsc --noEmit && npx vitest run
  ```
- **Gate 2 (Sanitizers, Integration & Supply Chain):**
  - Run real SQLite/Postgres container migrations + query tests.
  - C/C++: separate `ASan+UBSan` (`-fno-sanitize-recover=all`) and `TSan` builds (`ctest --output-on-failure`).
  - Unsafe Rust: `cargo +nightly miri test`.
  - Security: `gitleaks detect`, `pip-audit` / `cargo audit` / `npm audit`.
- **Gate 3 (Regression & Migration Safety):**
  - **Regression Guard:** Every bug-fix PR adds a test proven to fail without the fix.
  - **Migration Compat:** Run migrations forward against seeded data, run **previous** app version's read/write smoke tests against the migrated DB, then run new version.
  - **Zero Silent Skips:** Fail CI if new `pytest.mark.skip` / `#[ignore]` lacks a linked issue ID or if warnings (`-W error::ResourceWarning`) leak.

---

## 5. Structured Code Review Checklist

Reviewers verify **invariants and failure modes**, leaving formatting to automated linters.

### 1. Correctness & Edge Cases
- [ ] Boundary values handled: empty slice/string, `0`, negative numbers, `MAX_INT`, `None`/`null`, `NaN`/Inf, Unicode/multi-byte chars?
- [ ] Off-by-one checks (`<` vs `<=`), pagination boundary (last page vs exact page multiple), timezone-aware UTC timestamps?
- [ ] Partial failures and duplicate/retried requests handled idempotently?

### 2. Invariants & Error Handling
- [ ] Zero swallowed errors (`except Exception: pass`, `.unwrap()` on untrusted input, ignored C return codes)?
- [ ] Error chains preserved (`raise ... from e`, `#[source]`, `Error.cause`) without leaking stack traces or secrets to external callers?
- [ ] Domain invariants enforced in constructors/entities so illegal states cannot persist?

### 3. Concurrency & Resource Leaks
- [ ] Locks acquired in consistent global order; no lock held across network I/O, user callbacks, or `.await`?
- [ ] Every file, socket, DB connection/transaction, subprocess, and background task has deterministic cleanup (`with`, RAII, `defer`, `TaskGroup`) on both success and cancellation?
- [ ] Queues, caches, and retry loops are explicitly bounded (backpressure + max attempts + timeout)?

### 4. Security & Trust Boundaries
- [ ] Every external input validated at the boundary (schema, size limits, allowlists); SQL parameterized; no `shell=True`; paths verified with `is_relative_to`?
- [ ] Authentication AND object-level authorization (`owner_id`/`tenant_id`) enforced on every route/RPC?
- [ ] Outbound URLs checked against SSRF (private/metadata IP blocks + redirects disabled); secrets compared constant-time and absent from logs/VCS?

### 5. Performance & Complexity
- [ ] Zero N+1 queries inside loops (use `JOIN` / `WHERE id = ANY($1)` / DataLoader)?
- [ ] New DB queries backed by matching composite/partial indexes (`EXPLAIN ANALYZE` checked)?
- [ ] No accidental $O(N^2)$ scans/string concats, unbounded `SELECT *`, or blocking CPU/sync-I/O on async event loops?

### 6. Test Coverage & Maintainability
- [ ] Tests assert concrete resulting state and failure paths (not mock call counts or `"did not raise"`)?
- [ ] No `sleep()` synchronization, wall-clock dependence, unseeded randomness, or hardcoded TCP ports?
- [ ] Module boundaries & Dependency Rule respected (zero circular imports, domain stays I/O-free, dead code/debug prints removed)?
