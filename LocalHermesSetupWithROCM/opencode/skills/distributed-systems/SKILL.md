---
name: distributed-systems
description: Staff distributed systems and consensus engineering patterns — consistent hashing rings, vector clocks & causal sibling stores, SWIM gossip membership, fencing-token leases, C++20 Raft replicated logs, and crash-recoverable Two-Phase Commit.
---

# Staff Distributed Systems & Consensus

## Consistent Hashing Rings with Virtual Nodes
- **Sorted Ring Invariant:** Keep `sorted_keys` strictly sorted across BOTH `add_node` (`bisect.insort`) AND `remove_node` — never rebuild `sorted_keys` by iterating an unsorted dict (`self.ring.items()`), which silently breaks `bisect`.
- **Distinct Physical Replicas:** In `get_nodes(key, count)`, walk clockwise around `sorted_keys` wrapping with `% len(sorted_keys)` and deduplicate physical node IDs via a `visited` set until `count` or `len(physical_nodes)` distinct nodes are collected.

## SWIM Gossip Membership & Self-Refutation
- **Incarnation & State Precedence:** Higher `incarnation` always supersedes lower `incarnation`; at equal `incarnation`, strictly enforce `ALIVE < SUSPECT < DEAD` (never allow `DEAD` or `SUSPECT` to revert to `ALIVE` at the same incarnation).
- **Self-Refutation:** When a node receives a `SUSPECT` or `DEAD` rumor about `self_id` with `incarnation >= current_inc`, immediately refute by setting `self_id` to `(ALIVE, incarnation + 1)`.

## Fencing-Token Leases & Split-Brain Defense
- **Strictly Monotonic Tokens:** Every `acquire()` after expiry MUST allocate a globally monotonic `token += 1` (never reuse tokens). Reject `renew()` whenever `now >= expires_at`, owner mismatches, or token mismatches.
- **Storage-Side Watermark (`FencedStore`):** Track the highest accepted `fencing_token` per key; reject any write with `token < highest_seen` by raising `StaleTokenError` so a paused zombie leader can never corrupt newer writes.

## Raft Replicated Log & AppendEntries Consistency (C++20)
- **1-Based Indexing & Sentinel:** Initialize `entries_` with sentinel `{0, ""}` at index 0 so `last_log_index() = entries_.size() - 1` works uniformly.
- **Figure-2 Conflict Truncation Rule:** Reject `req.term < current_term_` and missing/mismatched `prev_log_index`/`prev_log_term`. Only truncate (`entries_.resize(idx)`) when an existing entry's `term` *conflicts* with an incoming entry's `term` — NEVER truncate a longer matching suffix on a stale shorter `AppendEntries` RPC! Advance `commit_index_ = std::max(commit_index_, std::min(req.leader_commit, last_log_index()))`.

## Two-Phase Commit (2PC) & Crash-Recovery WAL
- **JSONL WAL Framing:** Always write `json.dumps(record) + "\n"` followed by `flush()` + `os.fsync()` so WAL records never concatenate onto a single line.
- **No Abort After Durable `COMMITTED`:** Only catch participant failures/exceptions during Phase 1 (`prepare`) to transition to `ABORTED`. Once `COMMITTED` is durably logged to the WAL, NEVER wrap Phase 2 `commit()` in a `try/except` that converts a coordinator crash into an `ABORTED` decision — let the crash propagate so `recover()` replays `COMMITTED` idempotently.
