---
name: databases-storage
description: Senior database, SQLite, and storage-engine engineering patterns — atomic schema migrations, SQL-injection-safe query builders, BEGIN IMMEDIATE financial ledgers, CRC32 crash-safe WAL KV stores, C++20 LRU buffer pools, and Snapshot-Isolation MVCC.
---

# Senior Databases, SQLite & Storage Engines

## Transactional SQLite Schema Migrations
- **Foreign Keys & Tracking Table:** Enable `PRAGMA foreign_keys = ON` before running migrations and maintain a `schema_migrations(version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)` table.
- **Strict Ordering & Atomic Rollback:** Validate strictly ascending positive integer versions; wrap each pending migration + its tracking `INSERT` in a single transaction so any SQL error rolls back completely without recording the failed version, and keep repeated runs idempotent.

## SQL-Injection-Safe Query Builders & Keyset Pagination
- **Identifier Allowlisting:** Never interpolate table names, column names, or sort directions from untrusted input — validate every table/column against an explicit `allowed_columns` set (raising `ValueError` on mismatch) and restrict operators to a fixed whitelist (`=`, `!=`, `<`, `<=`, `>`, `>=`, `LIKE`).
- **Parameterized Values & Keyset Cursors:** Bind all filter values, cursor values, and limits exclusively with `?` placeholders (`(sql, params)`), never string formatting.

## Transactional Financial Ledgers (SQLite)
- **Explicit Transaction Control:** Open SQLite with `isolation_level=None`, enable `PRAGMA foreign_keys = ON`, enforce `CHECK(balance >= 0)` and `CHECK(amount > 0)` at the schema level, and wrap multi-step transfers in explicit `BEGIN IMMEDIATE` / `COMMIT` / `ROLLBACK` blocks.
- **Idempotency & Validation:** Make `tx_id` a `PRIMARY KEY`, reject duplicate transfers idempotently, reject self-transfers (`from_id == to_id`), and reject `bool`/non-positive amounts before opening a write lock.

## Crash-Safe Write-Ahead Log (WAL) KV Store
- **CRC32 Record Framing & Torn-Tail Recovery:** Frame records with `struct.pack(">IBII", crc, op, key_len, val_len) + key_bytes + val_bytes` (`crc = zlib.crc32(payload) & 0xFFFFFFFF`). Open in `"a+b"` (never write-only `"ab"` when replaying!), stop replay at the first truncated/corrupt CRC record, and `truncate(valid_offset)` + `flush()` + `os.fsync()`.
- **Atomic Compaction:** Never overwrite the live WAL in-place — write live keys to a `.tmp` sibling file, `flush()` + `os.fsync()`, close the old handle, `os.replace(tmp_path, path)`, and reopen `"a+b"`.

## Fixed-Frame Storage Engine LRU Page Buffer Pool (C++20)
- **Pinned vs Unpinned Separation:** Keep `frames_` in a fixed-size `std::vector<Page>` (zero raw `new`/`delete`), track unpinned evictable frames in an LRU `std::list<std::size_t>`, remove a frame from the LRU list whenever `pin_count` transitions `0 -> 1`, and push back to MRU only when `pin_count` drops back to `0`. Return `std::nullopt` if all frames are pinned.
- **Dirty Writeback Tracking:** Flush dirty victims to disk storage and increment `writeback_count_` before reusing their frame; clear `is_dirty = false` on explicit `flush_page` / `flush_all`.

## Snapshot-Isolation MVCC (First-Committer-Wins)
- **Versioned History & Tombstones:** Store `(commit_ts, value_or_tombstone)` lists per key with a unique sentinel `_TOMBSTONE = object()` so `None` vs deleted is unambiguous. Record `snapshot_ts = self.clock` at `begin()`.
- **RYOW + Snapshot Read + FCW Commit:** Check the transaction's local `write_set` first (Read-Your-Own-Writes), then scan committed versions in reverse for the newest entry with `commit_ts <= snapshot_ts`. On `commit()`, verify no key in `write_set` has a committed version with `commit_ts > snapshot_ts` (else abort and raise `ConflictError`), then increment `self.clock` once and append all writes atomically.
