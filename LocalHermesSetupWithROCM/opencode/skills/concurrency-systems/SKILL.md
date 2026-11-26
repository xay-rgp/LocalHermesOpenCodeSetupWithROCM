---
name: concurrency-systems
description: Staff concurrency, async, and lock-free engineering patterns — C++20 lock-free SPSC rings, AB-BA deadlock elimination with std::scoped_lock, TSan-clean atomic seqlocks, Python asyncio actor mailboxes & singleflight pools, and Node.js AbortSignal promise pools.
---

# Staff Concurrency, Async & Lock-Free Systems

## Lock-Free SPSC Ring Buffers (C++20, TSan-Clean)
- **Acquire/Release Memory Ordering:** Use `Capacity + 1` ring slots with `alignas(64)` cache-line-padded `std::atomic<std::size_t> head_` and `tail_` to avoid false sharing.
- **Producer (`try_push`):** Load own `tail_` with `memory_order_relaxed` and peer `head_` with `memory_order_acquire`; write `buffer_[t]`, then publish `tail_.store(next_t, memory_order_release)`.
- **Consumer (`try_pop`):** Load own `head_` with `memory_order_relaxed` and peer `tail_` with `memory_order_acquire`; read/move `buffer_[h]`, then publish `head_.store(next_h, memory_order_release)`.

## Deadlock-Free Multi-Lock & Non-Movable Mutexes (C++20, TSan-Clean)
- **Eliminate AB-BA & Self-Lock Deadlocks:** Handle `from == to` with a single `std::lock_guard`, and lock distinct mutexes with `std::scoped_lock lock(a.mtx, b.mtx)` (deadlock-avoidance algorithm).
- **Non-Movable Mutex Containers:** Store structs containing `std::mutex` in `std::deque<T>` (stable addresses, no reallocation moves), never `std::vector<T>`. Use `std::atomic<std::uint64_t>` for cross-thread counters (`fetch_add`/`load`) so TSan reports zero data races.

## Async Singleflight & Bounded Concurrency (Python `asyncio`)
- **Check In-Flight Table BEFORE Semaphore:** Never put `async with self._semaphore:` outside `if key in self._in_flight:` — otherwise duplicate callers queue behind the semaphore until the first finishes and pops `key`, defeating deduplication. Look up/insert `self._in_flight[key]` synchronously first, and acquire `self._semaphore` *inside* the shared task.
- **Never Swallow `asyncio.CancelledError`:** Never catch `BaseException` to return `None`; let `CancelledError` propagate cleanly while cleaning up `self._in_flight` in `finally`.

## Node.js Bounded Promise Pools & Abortable Retries
- **Index-Preserving Worker Pool:** Spawn `Math.min(concurrency, items.length)` worker coroutines sharing `let nextIndex = 0` and storing `results[i] = await workerFn(items[i], i)`; stop launching new items as soon as any worker sets `error`.
- **Clean Timer & AbortSignal Teardown:** In `retryWithTimeout`, register `signal.addEventListener("abort", onAbort, { once: true })`, always `clearTimeout(timeoutId)` and `signal.removeEventListener("abort", onAbort)` on settlement, and never retry after `signal.aborted`.
