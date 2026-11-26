---
name: algorithms-cs
description: "Apply data structures, graphs, DP, Big-O, and concurrency."
version: 1.0.0
author: Xay, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [algorithms, data-structures, big-o, graphs, dynamic-programming, concurrency]
    related_skills: [rust-development, cpp-c-development, python-development, debugging-mastery]
---

# Algorithms and Computer Science

Selecting, proving, and implementing optimal data structures, graph/tree/DP/sorting/searching algorithms, complexity analysis, and concurrent data structures for real-world engineering.

## When to Use

- Choosing the right data structure or algorithm for latency, throughput, or memory constraints
- Solving graph traversal, shortest path, dependency resolution, scheduling, string search, spatial indexing, or optimization problems
- Diagnosing quadratic `O(N^2)` blowups, stack overflows from deep recursion, or concurrent lock/memory-ordering bugs
- Don't use for: CRUD boilerplate where stdlib containers already meet performance requirements

## Complexity & Structure Selection Matrix

| Operation / Problem | Best Structure / Algorithm | Time | Space | Watch-Out |
|---|---|---|---|---|
| Exact lookup / dedup | Hash table (`dict`, `HashMap`) | O(1) avg | O(N) | Worst-case O(N) on hash collision DoS; SipHash/FxHash choice |
| Ordered range / predecessor | Balanced BST / B-Tree (`BTreeMap`) | O(log N) | O(N) | B-Tree beats RB-tree in RAM due to cache lines |
| Dynamic min/max / Top-K | Binary Heap (`heapq`, `BinaryHeap`) | O(log N) push/pop | O(K) | Lazy deletion for decrease-key in Dijkstra |
| Dynamic connectivity / MST | Disjoint Set Union (path compression + rank) | O(α(N)) ≈ O(1) | O(N) | Supports union only (not arbitrary split) |
| Range sum / point update | Fenwick Tree (BIT) / Segment Tree | O(log N) | O(N) | Segment tree + lazy prop for range updates |
| Prefix search / autocomplete | Trie / Radix Tree (Patricia) | O(L) | O(Σ·nodes) | Compress single-child chains (radix) for RAM |
| Unweighted shortest path | BFS | O(V + E) | O(V) | Mark visited on **enqueue**, not dequeue! |
| Weighted shortest path (w≥0) | Dijkstra (min-heap) / A* (admissible h) | O((V+E) log V) | O(V) | Fails with negative weights (use Bellman-Ford / SPFA) |
| DAG ordering / build deps | Kahn's BFS / DFS Topo Sort | O(V + E) | O(V) | Cycle iff output len < V |
| Monotonic threshold search | Binary Search on Answer | O(log(range)·check) | O(1) | Use `lo + (hi - lo) // 2` in fixed-width ints; prove loop invariant! |

## Core Engineering Rules

1. **Analyze amortized AND worst-case complexity, plus cache locality.** A flat contiguous `Vec`/array with `O(N)` scan often beats a pointer-chasing linked list or tree up to thousands of elements because of CPU L1/L2 prefetching.
2. **Guard recursion depth explicitly.** Never rely on unbounded recursion on user-controlled trees/graphs (Python hits `RecursionError` at ~1000 frames; C/Rust overflow the 8 MB stack). Convert deep DFS to an explicit stack.
3. **Prove binary search invariants.** Maintain half-open `[lo, hi)` with predicate `P(lo) == False` and `P(hi) == True`, loop `while lo < hi`, update `hi = mid` or `lo = mid + 1`. Eliminates infinite loops and off-by-one bugs.
4. **Formulate Dynamic Programming cleanly:** Define (1) state & meaning, (2) recurrence/transition, (3) base cases, (4) topological evaluation order, and (5) space optimization (rolling row/array).
5. **Respect concurrency memory models.** Atomics require explicit happens-before synchronization (`Release`/`Acquire` pairs), lock acquisition must follow a strict global total order to prevent deadlock, and lock-free structures must handle ABA (tagged pointers/epoch reclamation).

## Deep References

Load on demand with `skill_view("algorithms-cs", file_path="...")`:
- `references/data-structures-graphs-dp.md` — Trees, heaps, tries, Union-Find, segment/Fenwick trees, BFS/DFS/Dijkstra/A*/Bellman-Ford/Tarjan SCC/Kahn topo-sort, sorting stability & introsort/timsort, binary search template, DP patterns (knapsack, LIS, interval, bitmask, tree DP) with verified code templates.
- `references/concurrency-and-complexity.md` — Amortized analysis (potential method, dynamic arrays), Master Theorem, cache-aware layouts (SoA vs AoS), concurrency primitives (mutex, rwlock, semaphore, condvar, ring buffer/SPSC), memory ordering (`Acquire`/`Release`/`SeqCst`), ABA problem, deadlock Coffman conditions & prevention.

## Problem-Solving Procedure

1. **Specify input bounds and invariants.** Confirm `N`, value ranges, graph density (`E` vs `V^2`), mutability, latency SLA, and memory ceiling. Completion criterion: target Big-O time and space budgets are explicit (e.g., `N <= 10^5` forbids `O(N^2)`).
2. **Select structure & prove edge cases.** Check empty input, single element, all-equal elements, disconnected graphs, self-loops, parallel edges, negative weights, integer overflow, and cycles. Completion criterion: edge-case matrix is covered before coding.
3. **Implement clean reference solution + brute-force oracle.** For tricky algorithms (binary search, DP, segment trees, graph cuts), cross-check against a simple brute-force implementation on 1,000 small random inputs (stress testing!). Completion criterion: 0 mismatches across randomized property/stress tests.
4. **Benchmark on worst-case inputs.** Test adversarial inputs (already sorted, reverse sorted, deep skewed tree, dense graph) to confirm theoretical complexity holds in practice. Completion criterion: runtime scales as predicted when doubling `N`.

## Common Pitfalls

- **Hidden `O(N^2)` in "innocent" loops:** `list.pop(0)`, `x in list`, repeated string concatenation in a loop, or `re.compile` inside a hot loop turn linear algorithms quadratic. Use `collections.deque`, `set`, `"".join(...)`.
- **BFS visited timing bug:** Marking a node visited on pop instead of push allows the same node to be enqueued `O(deg)` times, blowing up memory and time exponentially on grids.
- **Unadmissible A* heuristic:** If `h(n)` overestimates true remaining cost, A* is no longer guaranteed optimal. For 4-way grids use Manhattan; for 8-way grids use Octile; for continuous 3D use Euclidean.
- **Memoization with unhashable/mutable state or huge key space:** Verify state space cardinality `|S|` fits RAM before caching; prefer bottom-up DP when recursion depth or dict overhead dominates.
- **Spurious wakeups in condition variables:** Never write `if (!ready) cv.wait(lock);` — ALWAYS loop `while (!ready) cv.wait(lock);`.
- **Robin-Hood HashMap Backward-Shift Deletion:** When shifting `table_[next]` back into `table_[idx]` during `erase()`, ALWAYS decrement `table_[idx].dist` (`--table_[idx].dist;`); forgetting to decrement `dist` breaks the Robin-Hood early-exit invariant (`dist > table_[idx].dist`) on subsequent `find()`/`insert_or_assign()` calls. Also check `find(key)` before starting the Robin-Hood swap loop to guarantee no duplicate keys are inserted after a swap.

## Verification

- Write unit tests for boundary cases (empty, n=1, duplicates, cycles, disconnected graphs, max bounds).
- Run a randomized differential stress test comparing the optimized algorithm against a naive oracle on small inputs.
- Measure scaling on `N` and `2N` inputs to confirm expected Big-O growth.
