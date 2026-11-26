# Concurrency, Memory Models, Cache Hierarchy & Complexity

Asymptotic & amortized analysis, CPU cache architecture, synchronization primitives, lock-free ring buffers, C++11/Rust memory ordering, ABA/reclamation, and deadlock prevention.

---

## 1. Complexity & Amortized Analysis

### Asymptotic Bounds & Traps
- $O(g(n))$ (upper), $\Omega(g(n))$ (lower), $\Theta(g(n))$ (tight). Distinguish **worst-case** (adversarial input), **expected randomized** (random pivot/hash seed), and **amortized** (average cost per operation over any worst-case sequence).
- **Hidden quadratic traps**: `vec.insert(0, x)`, `list.pop(0)`, `x in list`, repeated immutable string concatenation (`s += chunk`), or calling `sort()` inside a loop.

### Amortized Analysis: Accounting & Potential Method
Given state sequence $D_0 \to D_1 \to \dots \to D_m$ with true operation costs $c_i$:
$$\text{Amortized cost } \hat{c}_i = c_i + \Phi(D_i) - \Phi(D_{i-1}) \implies \sum_{i=1}^m c_i = \left(\sum_{i=1}^m \hat{c}_i\right) - \bigl(\Phi(D_m) - \Phi(D_0)\bigr)$$
If $\Phi(D_i) \ge \Phi(D_0)$ for all $i$, $\sum c_i \le \sum \hat{c}_i$.

- **Dynamic Array Doubling & Shrinking** (capacity $m$, size $n$; double at $n = m$, halve at $n = m/4$ — **hysteresis avoids ping-pong thrashing at $m/2$!**):
  - Accounting: charge 3 credits per `push` (1 writes item, 1 pays future move of itself, 1 pays future move of an older half-table element).
  - Potential: $\Phi(D) = |2n - m|$ (or $\max(2n - m,\, m/2 - n)$):
    - Non-resize `push` ($n \ge m/2$): $\hat{c} = 1 + 2 = 3 = O(1)$.
    - Doubling `push` ($n = m \to m'=2m$): $c = n + 1$, $\Delta\Phi = (2(n+1) - 2n) - (2n - n) = 2 - n \implies \hat{c} = (n+1) + (2-n) = 3 = O(1)$!
    - Halving `pop` ($n = m/4 \to m'=m/2$): $c = n + 1$, $\Delta\Phi = 0 - (m/2 - m/4) = -n \implies \hat{c} = 1 = O(1)$.
- **DSU & Splay Trees**: DSU with path compression + rank yields $O(\alpha(N))$ amortized ($\alpha(10^{80}) \le 5$). Splay trees use potential $\Phi = \sum_x \lfloor \log_2 \text{size}(x) \rfloor$ to prove $O(\log N)$ amortized per access/insert/delete.

### Master Theorem Quick Table ($T(n) = a\,T(n/b) + f(n),\; a \ge 1, b > 1$)
Let $c_{\text{crit}} = \log_b a$.

| Case | Condition on $f(n)$ | Tight Bound $T(n)$ | Canonical Example |
|---|---|---|---|
| **1 (Leaf-heavy)** | $f(n) = O(n^{c_{\text{crit}} - \epsilon})$ for $\epsilon > 0$ | $\Theta(n^{\log_b a})$ | Binary tree traversal: $2T(n/2)+O(1) \to \Theta(n)$ |
| **2 (Balanced)** | $f(n) = \Theta(n^{c_{\text{crit}}} \log^k n)$ for $k \ge 0$ | $\Theta(n^{\log_b a} \log^{k+1} n)$ | Merge sort ($k=0$): $2T(n/2)+\Theta(n) \to \Theta(n\log n)$ |
| **3 (Root-heavy)** | $f(n) = \Omega(n^{c_{\text{crit}} + \epsilon})$ + regularity $a f(n/b) \le c f(n)$ ($c<1$) | $\Theta(f(n))$ | Quickselect avg: $T(n/2)+\Theta(n) \to \Theta(n)$ |

*(Unequal splits like Median-of-Medians $T(n) = T(n/5) + T(7n/10) + \Theta(n)$ require **Akra-Bazzi**: since $1/5 + 7/10 < 1$, work decays geometrically $\to \Theta(n)$.)*

---

## 2. CPU Cache & Data-Oriented Memory Layout

| Level | Typical Size | Latency (approx.) | Bandwidth / Notes |
|---|---|---|---|
| Registers | ~KB | 0.25–0.5 ns (1 cycle) | Compiler-scheduled |
| L1d Cache | 32–48 KiB / core | ~1 ns (~4 cycles) | 64-byte cache lines |
| L2 Cache | 256 KiB–2 MiB / core | ~4 ns (~12 cycles) | Hardware spatial prefetcher watches linear strides |
| L3 Cache (LLC) | 16–96 MiB shared | ~15–25 ns (~40–70 cycles) | Coherence cross-core snoops/directories |
| Main RAM | GBs | ~70–100 ns (~200–300 cycles) | Random pointer chasing stalls CPU OoO window |

- **64-Byte Cache Line & Spatial Locality**: Accessing 1 `int32` loads 64 bytes (16 `int32`s). Contiguous `Vec<T>` linear scan is often 10–50× faster than pointer-chasing `LinkedList` or scattered heap nodes of identical Big-O.
- **False Sharing**: Two threads modifying *independent* variables (`counter_a`, `counter_b`) located on the **same 64-byte cache line** trigger continuous MESI `Invalidated` $\leftrightarrow$ `Modified` coherence bounces across cores!
  ```cpp
  struct alignas(64) PaddedCounter {
      std::atomic<uint64_t> value{0};
  }; // sizeof == 64: zero cross-core cache-line ping-pong
  ```
  (Note: on Apple Silicon / some ARM CPUs or Intel adjacent-sector prefetcher, `128`-byte alignment `std::hardware_destructive_interference_size` can avoid paired-line prefetching).
- **Struct-of-Arrays (SoA) vs Array-of-Structs (AoS)**:
  - **AoS**: `[ {pos, vel, name, mesh, hp}, ... ]` — updating `pos += vel * dt` pulls cold `name`/`mesh`/`hp` bytes into L1 cache and prevents AVX/NEON SIMD vectorization.
  - **SoA**: `{ pos_x[], pos_y[], pos_z[], vel_x[], ... }` (with cold metadata in a separate table) — 100% cache-line utilization and trivial SIMD auto-vectorization.

---

## 3. Synchronization Primitives & Lock-Free Ring Buffers

| Primitive | Ownership | Use Case & Pitfall |
|---|---|---|
| `Mutex` | Exclusive (owning thread unlocks) | Short critical sections; never hold across I/O or syscalls if avoidable |
| `RwLock` | Shared readers / exclusive writer | Beats `Mutex` ONLY when reads vastly outnumber writes AND hold times aren't tiny (atomic refcount bounces cache line on every read!). Watch writer starvation |
| `Semaphore` | Counting (any thread can `release`) | Bounding concurrency / resource pools (`N` permits) |
| `Condvar` | Stateless signal + external predicate | Wait for state change; **MUST loop** `while (!ready) cv.wait(lk);` to survive spurious & stolen wakeups! |

### Lock-Free Bounded SPSC Ring Buffer (Cache-Line Padded)
Power-of-2 capacity $N$, single producer, single consumer — requires **zero CAS/locks**, only `Acquire`/`Release` + cached shadow indices!
```cpp
#include <atomic>
#include <array>
#include <cstddef>

template <typename T, size_t CapacityPow2>
class SpscRing {
    static_assert((CapacityPow2 & (CapacityPow2 - 1)) == 0 && CapacityPow2 >= 2);
    static constexpr size_t kMask = CapacityPow2 - 1;

    alignas(64) std::atomic<size_t> head_{0}; // Written by producer
    alignas(64) size_t tail_cache_{0};        // Producer-local cached tail
    alignas(64) std::atomic<size_t> tail_{0}; // Written by consumer
    alignas(64) size_t head_cache_{0};        // Consumer-local cached head
    alignas(64) std::array<T, CapacityPow2> buf_{};

public:
    bool try_push(const T& item) {
        const size_t h = head_.load(std::memory_order_relaxed);
        const size_t next = h + 1;
        if (next - tail_cache_ > CapacityPow2) {
            tail_cache_ = tail_.load(std::memory_order_acquire);
            if (next - tail_cache_ > CapacityPow2) return false; // Full
        }
        buf_[h & kMask] = item;
        head_.store(next, std::memory_order_release); // Publishes buf_ write
        return true;
    }

    bool try_pop(T& out) {
        const size_t t = tail_.load(std::memory_order_relaxed);
        if (t == head_cache_) {
            head_cache_ = head_.load(std::memory_order_acquire);
            if (t == head_cache_) return false; // Empty
        }
        out = buf_[t & kMask];
        tail_.store(t + 1, std::memory_order_release); // Publishes slot free
        return true;
    }
};
```
**MPMC Ring Buffer (Vyukov Pattern)**: Add an `alignas(64)` `std::atomic<size_t> seq` per slot initialized to index `i`. Producer CAS-claims `head` when `slot.seq == pos`, writes data, sets `slot.seq = pos + 1` (`Release`); consumer CAS-claims `tail` when `slot.seq == pos + 1`, reads data, sets `slot.seq = pos + Capacity` (`Release`).

---

## 4. Memory Ordering (`Relaxed`, `Acquire`/`Release`, `SeqCst`)

Compilers and CPUs (especially ARM64/POWER weak models; x86-64 still reorders Store$\to$Load via store buffers!) reorder operations unless constrained by happens-before edges. **`volatile` in C/C++ is ONLY for MMIO/signals — it is NOT atomic and NOT thread synchronization.**

| Ordering | Guarantees | Typical Use & Hardware Cost |
|---|---|---|
| `relaxed` | Atomicity + single-variable modification order only | Counters, metrics, relaxed reads before CAS |
| `release` (store) | No prior read/write moves **after** this store | Publishing initialized data / unlocking |
| `acquire` (load) | No subsequent read/write moves **before** this load | Consuming published flag / acquiring lock |
| `acq_rel` | Both `acquire` and `release` on RMW (`CAS`/`fetch_add`) | Reference counting decrement (`fetch_sub(1, acq_rel)` + fence before `delete`) |
| `seq_cst` | Total global modification order across ALL `seq_cst` ops | Default safest choice; emits expensive store-load barrier (`MFENCE` / `DMB`) on x86 writes |

**Publication Pattern**:
```cpp
// Thread 1 (Producer)                      // Thread 2 (Consumer)
payload = 42;                               while (!ready.load(std::memory_order_acquire)) {}
ready.store(true, std::memory_order_release); // Guaranteed to observe payload == 42
```

---

## 5. Lock-Free Hazards: ABA & Safe Memory Reclamation

### The ABA Problem
In a lock-free Treiber stack (`pop`: read `head = A`, read `next = A->next`, `CAS(head, A, next)`):
1. Thread 1 reads `A` and `next = B`, then pauses before `CAS`.
2. Thread 2 pops `A`, pops `B`, **frees `A`**, allocates a new node at **reused address `A`**, pushes `A` back (`head -> A -> C`).
3. Thread 1 wakes up: `head == A` still holds! `CAS(head, A, B)` succeeds, pointing `head` at freed/corrupted `B`!

**Fix**: Attach a monotonic **generation tag** `(ptr, tag)` and update via double-width CAS (`cmpxchg16b` on x86-64, or packing a 16-bit tag into unused upper virtual-address bits on 48-bit-VA CPUs — beware 5-level paging `LA57`).

### Memory Reclamation (Why immediate `delete` crashes lock-free readers)
Even after unlinking a node via CAS, concurrent readers may still hold a raw pointer to it!
- **Hazard Pointers (HP)**: Each reader thread writes the pointer it is about to dereference into a shared per-thread HP slot (with `seq_cst`/StoreLoad fence), re-checks it is still reachable, and reads safely. Writers place retired nodes on a thread-local retire list and free only nodes absent from all threads' HP slots. **Pros**: Strictly bounded unfreed garbage ($O(T \cdot H)$). **Cons**: Store-load barrier on every pointer read.
- **Epoch-Based Reclamation (EBR, e.g., Rust `crossbeam-epoch`)**: Threads enter a critical section pinning the current global epoch `e` (`e, e+1, e+2`). Retired objects wait 2 full epoch advances before freeing. **Pros**: Near-zero read overhead (`Acquire` enter only). **Cons**: One stalled/descheduled thread holding an epoch pins all memory reclamation indefinitely.

---

## 6. Deadlock, Livelock & Starvation

### Deadlock: 4 Necessary Coffman Conditions
Deadlock occurs **iff all four** hold simultaneously:
1. **Mutual Exclusion**: Resource held non-shareably.
2. **Hold and Wait**: Thread holds lock $A$ while blocking for lock $B$.
3. **No Preemption**: Locks cannot be forcibly revoked.
4. **Circular Wait**: Cycle $T_1 \to L_1 \to T_2 \to L_2 \to T_1$.

### Prevention & Recovery Patterns
- **Break Circular Wait (Best Practice)**: Enforce a **strict global lock acquisition order** (by rank ID or memory address):
  ```cpp
  // C++17 atomic deadlock-free multi-lock (uses try_lock + backoff internally)
  std::scoped_lock lock(mtx_a, mtx_b);

  // Manual address ordering when acquiring two objects of same class:
  Mutex *first = &a.mtx < &b.mtx ? &a.mtx : &b.mtx;
  Mutex *second = &a.mtx < &b.mtx ? &b.mtx : &a.mtx;
  ```
- **Break Hold & Wait**: Release held lock if `try_lock()` on second lock fails; sleep for **randomized exponential backoff** (`rand() % (1 << attempt)`) before retrying.
- **Livelock**: Two threads symmetrically detect contention, release locks, and retry at identical cadence forever with zero progress. Fix with **asymmetric priority or randomized jitter** in backoff.
- **Starvation**: A thread waits indefinitely while others repeatedly cut ahead (e.g., reader-preferring `RwLock` starving a writer under continuous read traffic, or unfair spinlock). Fix with fair/FIFO ticket locks, writer-preference `RwLock`, or bounded retry escalation.

---

## 7. Concurrency Debugging & Verification Tools

- **Data Races & Lock Order Inversion**: Compile C/C++ with `-fsanitize=thread -g -O1` (ThreadSanitizer / TSan detects unsynchronized shared accesses AND lock-order cycles even before deadlock occurs!). In Rust: run `cargo +nightly miri test` or `TSAN_OPTIONS` / `loom` exhaustive interleaving model checking for lock-free algorithms.
- **False Sharing Profiling**: `perf c2c record -F 60000 -- ./app && perf c2c report` reveals contested `HITM` (Hit-Modified) cache lines and exact struct offsets causing cross-core ping-ponging.
- **Deadlock Triage on Live Processes**: `gdb -p <pid> -batch -ex "thread apply all bt"` or `eu-stack -p <pid>` to dump all thread stacks and trace the cycle of blocked mutex owners.
