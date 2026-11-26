# Data Structures, Graph Algorithms, Search & Dynamic Programming

Internals, trade-offs, invariants, and verified implementation templates for production engineering and algorithmic problem solving.

---

## 1. Data Structures: Internals & Selection Trade-offs

| Structure | Lookup / Query | Insert / Update | Space | Cache Behavior & Watch-Out |
|---|---|---|---|---|
| Dynamic Array (`Vec` / `list`) | $O(1)$ index | $O(1)$ amort. push, $O(N)$ mid | $O(N)$ | Best L1/L2 prefetch; growth factor $2\times$ vs $1.5\times$ |
| Hash Table (Open Addr.) | $O(1)$ avg / $O(N)$ worst | $O(1)$ amort. | $O(N)$ | Robin Hood / SwissTable SIMD beats chaining; tombstones hurt |
| Binary Heap | $O(1)$ min/max | $O(\log N)$ push/pop | $O(N)$ | Implicit array (`2i+1`, `2i+2`); $O(N)$ bottom-up `heapify` |
| B-Tree (`BTreeMap`) | $O(\log N)$ | $O(\log N)$ | $O(N)$ | High fanout $B$ fits cache lines; 3–10× faster than RB-tree |
| Trie / Radix Tree (ART) | $O(L)$ key len | $O(L)$ | $O(\Sigma \cdot \text{nodes})$ | Compress single-child chains (Radix/Patricia) to save RAM |
| Disjoint Set Union (DSU) | $O(\alpha(N))$ `find` | $O(\alpha(N))$ `union` | $O(N)$ | Path compression + union by rank/size; supports union only |
| Fenwick Tree (BIT) | $O(\log N)$ prefix | $O(\log N)$ point add | $O(N)$ | Invertible ops (`+`, `^`) only; 1-indexed `i += i & -i` |
| Segment Tree + Lazy Prop | $O(\log N)$ range | $O(\log N)$ range | $O(4N)$ | General monoids (`min`, `max`, affine); push lazy before descend |

### Critical Internals
- **Dynamic array growth**: Factor $1.5\times$ allows previously freed memory blocks to eventually be reused by the allocator ($\sum_{i=0}^{k-1} 1.5^i > 1.5^k$ for large $k$), whereas $2\times$ never lets summed old blocks match the new allocation size. Always call `reserve(n)` when upper bound is known to eliminate reallocations and iterator/pointer invalidation.
- **Open addressing vs chaining**: Open addressing (linear probing, Robin Hood, SwissTable control bytes) stores entries inline—zero pointer-chasing—but requires load factor $\le 0.75\text{–}0.875$ and degrades if deletions leave tombstones without periodic rehash. Use `SipHash` on untrusted keys (HashDoS defense); use `FxHash`/`ahash` on trusted internal IDs.
- **Disjoint Set Union (DSU)**:
  ```python
  class DSU:
      def __init__(self, n: int) -> None:
          self.parent = list(range(n))
          self.size = [1] * n
          self.components = n

      def find(self, x: int) -> int:
          while self.parent[x] != x:
              self.parent[x] = self.parent[self.parent[x]]  # Path halving (iterative, no stack overflow!)
              x = self.parent[x]
          return x

      def union(self, a: int, b: int) -> bool:
          ra, rb = self.find(a), self.find(b)
          if ra == rb:
              return False
          if self.size[ra] < self.size[rb]:
              ra, rb = rb, ra
          self.parent[rb] = ra
          self.size[ra] += self.size[rb]
          self.components -= 1
          return True
  ```
- **Fenwick Tree (BIT)**:
  ```python
  class Fenwick:
      def __init__(self, n: int) -> None:
          self.n = n
          self.tree = [0] * (n + 1)

      def add(self, idx: int, delta: int) -> None:  # 0-indexed external API
          i = idx + 1
          while i <= self.n:
              self.tree[i] += delta
              i += i & -i

      def prefix_sum(self, idx: int) -> int:  # sum [0..idx] inclusive
          s = 0
          i = idx + 1
          while i > 0:
              s += self.tree[i]
              i -= i & -i
          return s

      def range_sum(self, l: int, r: int) -> int:
          return self.prefix_sum(r) - (self.prefix_sum(l - 1) if l > 0 else 0)
  ```
- **Lazy Segment Tree** (range add + range sum, 0-indexed `[l, r)` queries):
  ```python
  class LazySegTree:
      def __init__(self, arr: list[int]) -> None:
          self.n = len(arr)
          self.size = 1
          while self.size < self.n:
              self.size <<= 1
          self.tree = [0] * (2 * self.size)
          self.lazy = [0] * (2 * self.size)
          for i, v in enumerate(arr):
              self.tree[self.size + i] = v
          for i in range(self.size - 1, 0, -1):
              self.tree[i] = self.tree[2 * i] + self.tree[2 * i + 1]

      def _apply(self, node: int, seg_len: int, val: int) -> None:
          self.tree[node] += val * seg_len
          if node < self.size:
              self.lazy[node] += val

      def _push(self, node: int, seg_len: int) -> None:
          if self.lazy[node] != 0:
              half = seg_len >> 1
              self._apply(2 * node, half, self.lazy[node])
              self._apply(2 * node + 1, half, self.lazy[node])
              self.lazy[node] = 0

      def range_add(self, ql: int, qr: int, val: int) -> None:
          def _upd(node: int, nl: int, nr: int) -> None:
              if qr <= nl or nr <= ql:
                  return
              if ql <= nl and nr <= qr:
                  self._apply(node, nr - nl, val)
                  return
              self._push(node, nr - nl)
              mid = (nl + nr) >> 1
              _upd(2 * node, nl, mid)
              _upd(2 * node + 1, mid, nr)
              self.tree[node] = self.tree[2 * node] + self.tree[2 * node + 1]
          _upd(1, 0, self.size)

      def range_sum(self, ql: int, qr: int) -> int:
          def _qry(node: int, nl: int, nr: int) -> int:
              if qr <= nl or nr <= ql:
                  return 0
              if ql <= nl and nr <= qr:
                  return self.tree[node]
              self._push(node, nr - nl)
              mid = (nl + nr) >> 1
              return _qry(2 * node, nl, mid) + _qry(2 * node + 1, mid, nr)
          return _qry(1, 0, self.size)
  ```

---

## 2. Graph Algorithms

### Traversal Invariants
- **BFS** ($O(V + E)$): Shortest path on unweighted graphs. **Critical bug**: mark `visited[v] = True` upon **enqueueing**, never upon dequeueing (otherwise a grid vertex gets queued $O(\text{deg})$ times $\implies$ exponential blowup). For 0/1 edge weights, use **0-1 BFS** with a `deque`: push weight-0 neighbors to `appendleft`, weight-1 neighbors to `append`.
- **Iterative DFS** ($O(V + E)$): Never trust recursive DFS on $V \ge 10^4$ arbitrary graphs (Python `RecursionError` ~1000 frames; C/Rust 8 MB stack overflow). Simulate pre/post-order with `(node, exiting_bool)`:
  ```python
  stack = [(root, False)]
  visited = set()
  while stack:
      u, exiting = stack.pop()
      if exiting:
          post_order.append(u)
          continue
      if u in visited:
          continue
      visited.add(u)
      stack.append((u, True))
      for v in reversed(adj[u]):
          if v not in visited:
              stack.append((v, False))
  ```

### Shortest Paths
- **Dijkstra with Lazy Heap** ($O((V + E)\log V)$, requires $w \ge 0$):
  ```python
  import heapq
  INF = 10**18
  dist = [INF] * n
  dist[src] = 0
  pq = [(0, src)]
  while pq:
      d, u = heapq.heappop(pq)
      if d > dist[u]:  # Lazy deletion skips stale entries!
          continue
      if u == dst:
          break
      for v, w in adj[u]:
          nd = d + w
          if nd < dist[v]:
              dist[v] = nd
              heapq.heappush(pq, (nd, v))
  ```
- **A\* Search**: Priority key $f(n) = g(n) + h(n)$.
  - **Admissible** ($h(n) \le h^*(n)$ true remaining cost): guarantees optimality in tree search.
  - **Consistent/Monotone** ($h(u) \le w(u, v) + h(v)$): guarantees first pop of `u` is optimal (no re-expansion needed, same `d > g[u]` guard as Dijkstra).
  - Heuristics: 4-way grid $\to$ Manhattan $|\Delta x| + |\Delta y|$; 8-way grid $\to$ Octile $\max(|\Delta x|, |\Delta y|) + (\sqrt{2} - 1)\min(|\Delta x|, |\Delta y|)$; continuous space $\to$ Euclidean $\sqrt{\Delta x^2 + \Delta y^2 + \Delta z^2}$.
- **Bellman-Ford** ($O(VE)$): Handles negative weights. Relax all $E$ edges $V - 1$ times (early-exit if an iteration makes 0 changes). A $V$-th pass that relaxes any edge detects a reachable **negative cycle** (run $V$ more passes marking affected nodes $-\infty$ if finding all impacted targets).

### Ordering, Connectivity & MST
- **Kahn's Topological Sort** ($O(V + E)$): Track `indeg[v]`. Seed queue (or min-heap for lexicographically smallest order) with `indeg == 0`. Decrement neighbor `indeg` on pop. **Cycle iff `len(order) < V`**.
- **Tarjan's SCC** ($O(V + E)$): Maintain `disc[u]`, `low[u]`, `on_stack[u]`, and active stack. When `low[u] == disc[u]`, pop stack up to `u` to form one strongly connected component. Condensing SCCs turns any directed graph into a DAG!
- **MST**: **Kruskal** ($O(E \log E)$, sort edges + DSU — optimal for sparse graphs or pre-sorted edges); **Prim** ($O((V+E)\log V)$ heap or $O(V^2)$ array-scan without heap for dense $E \approx V^2$ graphs).

---

## 3. Sorting & Proven Binary Search

### Sorting Algorithms
| Algorithm | Best | Average | Worst | Space | Stable | Where Used & Why |
|---|---|---|---|---|---|---|
| **Timsort** | $O(N)$ | $O(N\log N)$ | $O(N\log N)$ | $O(N)$ | Yes | Python `sort`, Java Objects; exploits natural sorted runs + galloping merge |
| **Introsort** | $O(N\log N)$ | $O(N\log N)$ | $O(N\log N)$ | $O(\log N)$ | No | C++ `std::sort`, Rust `sort_unstable`; Quicksort $\to$ Heapsort at depth $2\lfloor\log_2 N\rfloor$ + Insertion sort ($\le 16$) |
| **LSD Radix Sort** | $O(d(N+B))$ | $O(d(N+B))$ | $O(d(N+B))$ | $O(N+B)$ | Yes | Fixed-width integers/keys (e.g., 4 passes of 8-bit buckets for `uint32_t`); beats comparison sorts for large $N$ |

**Stability Rule**: Multi-column sorting (`order by dept asc, salary desc`) relies on stability when sorting sequentially by secondary key first, or using tuple keys.

### Proven Half-Open Binary Search (`[lo, hi)`)
Maintain invariant: **`P(x)` is monotonic (`False, ..., False, True, ..., True`)**, `P(lo - 1)` conceptually `False`, `P(hi)` conceptually `True`. Goal: return smallest `x` in `[0, n)` where `P(x)` is `True` (or `n` if all `False`).
```python
def lower_bound(lo: int, hi: int, pred) -> int:
    """Returns smallest x in [lo, hi) with pred(x) == True, or hi if none."""
    while lo < hi:
        mid = lo + (hi - lo) // 2  # Overflow-safe in C++/Rust/Java
        if pred(mid):
            hi = mid
        else:
            lo = mid + 1
    return lo
```
- **Upper bound (`first > target`)**: `pred = lambda i: arr[i] > target`.
- **Binary Search on Answer**: Whenever feasibility `feasible(X)` is monotonic (e.g., minimum ship capacity / maximum min-distance), call `lower_bound(min_ans, max_ans + 1, feasible)` (for maximize-minimum problems, negate predicate: search smallest `X` where `not feasible(X)`, then answer is `lo - 1`).
- **Floating-point search**: Run a fixed **60–100 iterations** (`for _ in range(80):`) instead of `while hi - lo > eps:` (avoids infinite loop when `eps` falls below IEEE-754 float64 ULP at large magnitudes!).

---

## 4. Dynamic Programming Templates

Every DP requires 5 explicit steps: **(1) State meaning, (2) Transition, (3) Base cases, (4) Topological order, (5) Space optimization**.

### 1. 0/1 Knapsack vs Unbounded Knapsack (1D Space-Optimized)
```python
# 0/1 Knapsack: iterate capacity BACKWARD so each item is used at most once
dp = [0] * (W + 1)
for w, v in items:
    for c in range(W, w - 1, -1):
        dp[c] = max(dp[c], dp[c - w] + v)

# Unbounded Knapsack: iterate capacity FORWARD
for w, v in items:
    for c in range(w, W + 1):
        dp[c] = max(dp[c], dp[c - w] + v)
```

### 2. Longest Increasing Subsequence (LIS) — $O(N \log N)$
`tails[k]` = smallest possible ending value of an increasing subsequence of length `k + 1`.
```python
from bisect import bisect_left  # Use bisect_right for non-decreasing (<=)

def lis_length(nums: list[int]) -> int:
    tails: list[int] = []
    for x in nums:
        idx = bisect_left(tails, x)
        if idx == len(tails):
            tails.append(x)
        else:
            tails[idx] = x
    return len(tails)
```

### 3. Interval DP ($O(N^3)$)
State: `dp[i][j]` = optimal cost on subarray `nums[i..j]` inclusive. Evaluate in increasing length `L`.
```python
dp = [[0] * n for _ in range(n)]
for length in range(2, n + 1):
    for i in range(0, n - length + 1):
        j = i + length - 1
        best = INF
        for k in range(i, j):  # Split point
            best = min(best, dp[i][k] + dp[k + 1][j] + merge_cost(i, k, j))
        dp[i][j] = best
```

### 4. Bitmask TSP & Submask Enumeration
```python
# TSP: dp[mask][u] = min cost visiting nodes in `mask`, ending at `u` (start=0)
dp = [[INF] * n for _ in range(1 << n)]
dp[1][0] = 0
for mask in range(1, 1 << n):
    if not (mask & 1):
        continue
    for u in range(n):
        if not (mask & (1 << u)) or dp[mask][u] == INF:
            continue
        rem = ((1 << n) - 1) ^ mask
        while rem:
            lsb = rem & -rem
            v = lsb.bit_length() - 1
            nmask = mask | lsb
            dp[nmask][v] = min(dp[nmask][v], dp[mask][u] + cost[u][v])
            rem ^= lsb

# Enumerating ALL non-empty submasks of `mask` across all masks takes O(3^N) total!
sub = mask
while sub:
    # process `sub`
    sub = (sub - 1) & mask
```

### 5. Tree DP (Iterative Post-Order)
Example: Maximum Weight Independent Set on a tree (`dp0[u]` = exclude `u`, `dp1[u]` = include `u`).
```python
order, parent = [], [-1] * n
stack = [0]
while stack:
    u = stack.pop()
    order.append(u)
    for v in adj[u]:
        if v != parent[u]:
            parent[v] = u
            stack.append(v)

dp0, dp1 = [0] * n, weights[:]
for u in reversed(order):  # Bottom-up children -> parent
    for v in adj[u]:
        if v != parent[u]:
            dp0[u] += max(dp0[v], dp1[v])
            dp1[u] += dp0[v]
ans = max(dp0[0], dp1[0])
```

---

## 5. Verification & Edge-Case Checklist
- **Graph edge cases**: disconnected components, $V=1, E=0$, self-loops (`u == v`), parallel multiedges (take `min` weight), negative cycles, 0-indexed vs 1-indexed conversion.
- **Overflow & precision**: in fixed-width ints (`i32`/`i64`), use `INF = INT64_MAX // 4` so `INF + w` never wraps negative!
- **Differential stress test**: compare optimized DP / SegTree / Dijkstra against a 15-line brute-force oracle across 2,000 random small inputs ($N \le 8$) before trusting edge cases.
