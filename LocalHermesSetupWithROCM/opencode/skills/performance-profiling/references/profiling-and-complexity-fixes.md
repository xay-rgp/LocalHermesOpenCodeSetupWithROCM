# Profiling & Complexity Remediation Reference

## 1. Algorithmic Complexity Fixes ($O(N^2) \to O(N)$)

### Symptom in `profile_harness.py`
High `tottime_ms` inside a function containing a nested `for` loop, list comprehension, or `if x in allowed_list:`.

### Remediation Pattern
```python
# SLOW: O(N * M) linear scan + repeated regex compile inside loop
for event in events:
    if event["actor"] in allowed_actors_list:
        m = re.search(r"^user_(\d+)$", event["actor"])
        ...

# FAST: O(N + M) hash set + pre-compiled regex outside loop
ACTOR_RE = re.compile(r"^user_(\d+)$")
allowed_set = set(allowed_actors_list)
for event in events:
    actor = event["actor"]
    if actor in allowed_set:
        m = ACTOR_RE.search(actor)
        ...
```

## 2. Eliminating N+1 SQLite Queries & Auto-Commit Thrashing

### Symptom in `profile_harness.py`
High `cumtime_ms` in a DB enrichment or persistence method with thousands of `execute` / `commit` calls.

### Remediation Pattern
1. **Create an index on lookup columns** (`CREATE INDEX IF NOT EXISTS idx_table_col ON table(col)`).
2. **Batch-fetch lookup tables into a dictionary** (or chunked `WHERE key IN (?, ?, ...)` queries) instead of issuing one `SELECT` per event.
3. **Wrap batch writes in a single transaction** (`with conn: conn.executemany(...)`) instead of calling `conn.commit()` on every row.

```python
# FAST: Single indexed lookup + single transaction batch insert
with conn:
    conn.execute("CREATE INDEX IF NOT EXISTS idx_accounts_id ON accounts(account_id)")
    account_map = dict(
        conn.execute("SELECT account_id, tier FROM accounts").fetchall()
    )
    conn.executemany(
        "INSERT INTO enriched_events (event_id, tier, latency_ms) VALUES (?, ?, ?)",
        rows_to_insert,
    )
```

## 3. Eliminating Memory Leaks (`tracemalloc` Growth Across Iterations)

### Symptom in `profile_harness.py`
`memory_leak_check.leaking == true` and `retained_kib_series` increases monotonically on each iteration.

### Common Root Causes & Fixes
1. **Class-level or module-level mutable accumulator (`_AUDIT_LOG = []`, `_CACHE = {}`):**
   - Never append unbounded event batches to a class attribute or module global without eviction.
   - Replace with a bounded `collections.deque(maxlen=64)` or clear per-run temporary buffers on completion.
2. **`@functools.lru_cache(maxsize=None)` on instance methods:**
   - Pins `self` forever. Use a bounded module-level cache on primitive keys or `maxsize=256`.
