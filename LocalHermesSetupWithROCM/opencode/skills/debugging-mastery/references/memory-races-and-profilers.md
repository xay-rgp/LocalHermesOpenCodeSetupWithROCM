# Stack Traces, Compiler/Linker Diagnostics, Sanitizers, Races, and Profiling

## 1. Decoding Stack Traces & Chained Exceptions

| Runtime | Trace Reading Order | Key Diagnostic Flags / Commands |
|---|---|---|
| **Python** | **Bottom -> up** (bottom = root exception; walk up to first project frame) | `PYTHONFAULTHANDLER=1` (prints C-crash stack), `python3 -m pdb -c continue app.py` |
| **Rust** | **Top -> down** from panic line (`panicked at ...`) to your crate frame | `RUST_BACKTRACE=1` (short), `RUST_BACKTRACE=full` (includes runtime/std frames) |
| **C / C++** | **`#0` -> `#N`** (`#0` is crash PC, often `libc`; first `#N` in user code is suspect) | `gdb -batch -ex run -ex "bt full" --args ./app` / `coredumpctl gdb` |
| **JS / TS** | **Top -> down** (line 1 = error; first frame outside `node_modules`/Node internals) | `node --enable-source-maps dist/index.js`, inspect `err.cause` |

### Python Chained Exceptions & `ExceptionGroup`
- **`The above exception was the direct cause...` (`__cause__`):** Explicit `raise NewError(...) from orig_exc`. Fix the **topmost** traceback first!
- **`During handling of the above exception, another exception occurred` (`__context__`):** An exception happened inside an `except:` or `finally:` block while handling the first error. Fix BOTH — the cleanup bug masks the real error.
- **`ExceptionGroup` (`TaskGroup`):** Read every sub-exception leaf (`except* ValueError as eg:`) rather than stopping at the wrapper summary.

### C/C++ Stripped Address & Demangling Tools
```bash
# Convert crash instruction offsets to file:line (requires debug symbols / separate .debug)
addr2line -e ./build/server -f -C 0x404a12 0x40219c

# Demangle C++ or Rust symbols manually
c++filt _ZN5myapp5Order7approveEmd
```

### Rust Error Chains
Print full causal chains in binaries using `{:#}` or `.chain()` (`anyhow`):
```rust
eprintln!("fatal: {err:#}"); // prints "failed config -> permission denied" instead of top frame only
```

---

## 2. Decoding Compiler & Linker Errors

### C++ Template Instantiation Traces
1. **Fix ONLY the first error** — subsequent errors cascade from a broken AST/type.
2. Skip the middle wall of `in instantiation of ...` / `required from ...`; read:
   - The **top line**: caller site (`main.cpp:42:10: error: no matching function for call to ...`).
   - The **bottom root `error:`**: exact type mismatch (`cannot convert 'const Foo' to 'Foo&'`).
   - `note: candidate template ignored: constraints not satisfied` (C++20 concepts pinpoint the exact failed clause).

### GCC / Clang / `ld` Linker Failures
| Linker Message | Root Cause | Exact Fix |
|---|---|---|
| `undefined reference to 'foo'` (C lib) | Static library `.a` placed **before** object that uses it (`ld` scans left-to-right once!) | Put dependents BEFORE dependencies: `g++ main.o -lapp -lcore -lpthread` (or `-Wl,--start-group -la -lb -Wl,--end-group`) |
| `undefined reference to 'foo(int)'` | C++ caller compiled C header without `extern "C"`, causing C++ name mangling mismatch | Verify with `nm -C libfoo.a \| grep foo` (`T foo` = C, `T foo(int)` = C++); wrap header in `extern "C" { #include "foo.h" }` |
| `multiple definition of 'x'` | Non-`inline` function or non-`extern` global defined in a `.h` included by 2 `.cpp` files | Declare `extern int x;` in `.h` + define once in `.cpp`, or mark functions/vars `inline` (C++17+) / `static` |
| `undefined reference to 'vtable for Base'` | First non-inline virtual method declared in class has no out-of-line definition | Define the key virtual method or `Base::~Base() = default;` in a `.cpp` file |

### Rust Borrow & Lifetime Diagnostics
| Code | Meaning | Standard Fix |
|---|---|---|
| `E0502` | Cannot borrow as `&mut` while `&` immutable borrow is still live | End immutable borrow before mutating (clone small value, compute index before `push`, or split struct fields) |
| `E0499` | Two overlapping `&mut` borrows on same struct | Extract disjoint field borrows (`let (a, b) = (&mut s.a, &mut s.b);`) instead of two `&mut self` methods |
| `E0597` | Borrowed value does not live long enough | Watch **reverse drop order** of locals or temporaries dropped at `;`; bind temporary to a `let` BEFORE the borrower |
| `E0382` | Use of moved value | Borrow `&x`, clone deliberately, or return ownership back out |
| `future cannot be sent between threads` | `!Send` value (`Rc`, `std::sync::MutexGuard`) held across `.await` | Scope lock inside `{ let g = m.lock().unwrap(); ... }` so guard drops before `.await` |

---

## 3. Memory Debugging & Leak Hunting

### ASan + LSan + UBSan (C / C++)
Combine ASan and UBSan in one debug target (never combine ASan with TSan or Valgrind):
```bash
clang++ -O1 -g -fno-omit-frame-pointer \
  -fsanitize=address,undefined -fno-sanitize-recover=all \
  src/*.cpp -o build/app_san

ASAN_OPTIONS=detect_leaks=1:halt_on_error=1:abort_on_error=1:detect_stack_use_after_return=1 \
  ./build/app_san
```
- `-fno-sanitize-recover=all`: forces UBSan to **exit non-zero immediately** on signed overflow, misaligned load, null deref, or invalid shift instead of logging and continuing.
- **Reading an ASan UAF report (3 stacks):**
  1. **Access stack (`READ/WRITE of size N`):** where the dangling pointer was dereferenced.
  2. **Freed stack (`freed by thread T0 here`):** where `free`/`delete`/vector reallocation released it.
  3. **Allocation stack (`previously allocated by thread T0 here`):** original owner.
- Use `LSAN_OPTIONS=suppressions=lsan.supp` only for verified third-party C library one-time allocations.

### Valgrind (When You Cannot Recompile)
```bash
valgrind --leak-check=full --show-leak-kinds=all --track-origins=yes --error-exitcode=1 ./build/app
```
- **`definitely lost`:** True leak (no pointer reaches the block). Fix immediately.
- **`indirectly lost`:** Reachable only from a `definitely lost` parent node. Fixing parent fixes these.
- **`possibly lost`:** Interior pointer (common with custom arenas/C++ `std::string` SSO offsets).
- **`still reachable`:** Global/singleton cache not freed before `exit()`.
- `--track-origins=yes` pinpoints the exact allocation/stack variable responsible for `Conditional jump or move depends on uninitialised value(s)`.

### Python Memory Leaks (`tracemalloc` & `memray`)
`tracemalloc` tracks Python VM allocations; `memray` captures **both Python AND C/C++ extension** (`numpy`, `torch`, `lxml`) allocations:
```python
# Compare two steady-state checkpoints after warmup (distinguishes plateau vs true leak!)
import gc, tracemalloc
tracemalloc.start(15)
run_batches(10)  # warm up pools/caches first
gc.collect()
snap1 = tracemalloc.take_snapshot()
run_batches(100)
gc.collect()
snap2 = tracemalloc.take_snapshot()

for stat in snap2.compare_to(snap1, "traceback")[:5]:
    print(stat)
    print("\n".join(stat.traceback.format()))
```
```bash
# memray CLI (tracks native + Python heap with flamegraphs and leak mode)
memray run -o out.bin app.py
memray flamegraph --leaks out.bin -o leaks.html
```

### Node.js / JS Heap Snapshots
```bash
# Capture heap snapshots on demand via SIGUSR2 without restarting production/staging:
node --heapsnapshot-signal=SIGUSR2 --enable-source-maps dist/server.js
kill -USR2 <PID>   # before workload (Snapshot 1)
# run N requests...
kill -USR2 <PID>   # after workload (Snapshot 2)
```
Load snapshots into Chrome DevTools Memory tab -> select **Snapshot 2** -> switch view to **"Objects allocated between Snapshot 1 and 2"** -> sort by **Retained Size** -> inspect **Retainers** tree (often forgotten event listeners, closures capturing huge buffers, or unbounded `Map` caches). Also watch GC thrashing with `node --trace-gc`.

---

## 4. Concurrency Debugging & Race Amplification

### ThreadSanitizer (TSan)
```bash
clang++ -O1 -g -fno-omit-frame-pointer -fsanitize=thread src/*.cpp -o build/app_tsan
TSAN_OPTIONS="halt_on_error=1:second_deadlock_stack=1" ./build/app_tsan

# Rust (nightly):
RUSTFLAGS="-Z sanitizer=thread" cargo +nightly test -Z build-std --target x86_64-unknown-linux-gnu
```
- **Data Race report:** Look at `Write of size N at 0x... by thread T2` vs `Previous read/write of size N at 0x... by thread T1` and `Mutexes held: []` (missing shared lock or unprotected atomic!).
- **`lock-order-inversion (potential deadlock)`:** TSan builds a lock graph at runtime and reports `M1 -> M2` vs `M2 -> M1` **even before the deadlock actually hangs**.

### Diagnosing Hung Deadlocks
1. **C / C++ / Rust (`gdb`):**
   ```bash
   gdb -p <PID> -batch -ex "set pagination off" -ex "thread apply all bt"
   ```
   Look for threads blocked in `futex` / `__lll_lock_wait` / `pthread_mutex_lock`. Print lock owner in GDB: `p mutex.__data.__owner` (matches LWP ID in `info threads`).
2. **Python (`py-spy` + `faulthandler`):**
   ```bash
   py-spy dump --pid <PID> --gil   # shows every thread stack + who holds the GIL + native frames
   ```
   Or register `faulthandler.register(signal.SIGUSR1)` at startup so `kill -USR1 <PID>` dumps all thread tracebacks instantly.
3. **Rule to prevent deadlocks:** Enforce a strict global lock acquisition order (`id(a) < id(b)`), use `std::scoped_lock(m1, m2)` in C++, and **never hold a lock across external I/O, callbacks, or `.await`**.

### Turning 1% Race Flakes into 90% Reproducers
1. **Tight stress loop until first failure:**
   ```bash
   for i in $(seq 1 500); do ./build/test_race || { echo "FAILED on iter $i"; break; }; done
   # Python: pytest -x --count=200 tests/test_concurrency.py
   ```
2. **Synchronize threads onto the starting line with a Barrier:**
   ```python
   barrier = threading.Barrier(8)
   def worker():
       barrier.wait()  # forces all 8 threads into the race window simultaneously
       target.mutate()
   ```
3. **Perturb scheduler timing:** Force context switches inside critical windows in test builds (`std::this_thread::yield()`, `sched_yield()`, `await asyncio.sleep(0)`), pin cores (`taskset -c 0-1`), or add background CPU load (`stress-ng --cpu 8`).
4. **Deterministic Time-Travel Debugging with `rr` (Linux x86_64/ARM64):**
   ```bash
   rr record --chaos ./build/flaky_test   # --chaos randomizes scheduling to trigger races
   rr replay                              # enters gdb at deterministic replay
   # Inside rr gdb: run to crash -> set hardware watchpoint on corrupted address -> reverse-continue!
   (rr) continue
   (rr) watch -l *(int*)0x7fff1234abcd
   (rr) reverse-continue                  # jumps BACKWARD to exact instruction that corrupted memory!
   ```

---

## 5. Automated Regression Hunting (`git bisect`)

```bash
git bisect start HEAD v2.4.0          # bad = HEAD, good = v2.4.0
git bisect run ./repro.sh
# Inspect offending commit, then restore HEAD:
git bisect reset
```

### Exit Code Contract (Critical!)
- **`0`**: commit is **good**.
- **`1..124` or `126..127`**: commit is **bad**.
- **`125`**: commit **cannot be tested / skip** (build failure, missing migration, unrelated breakage).
- **`>= 128` (including signals like `SIGSEGV` = `139`!)**: **ABORTS `git bisect` immediately!**

### Safe `repro.sh` Wrapper Template
Always wrap binaries that might segfault or hang so signals map to `1` instead of aborting bisect, and failed builds return `125`:
```bash
#!/usr/bin/env bash
set -u

# 1. Build step: broken intermediate commits return 125 (skip)
cmake -B /tmp/bisect-build -DCMAKE_BUILD_TYPE=Debug >/dev/null 2>&1 || exit 125
cmake --build /tmp/bisect-build -j"$(nproc)" >/dev/null 2>&1 || exit 125

# 2. Test step: map timeout/segfault (>127) to exit 1 (bad) so bisect continues!
timeout 15s /tmp/bisect-build/test_repro >/dev/null 2>&1
rc=$?
if [ "$rc" -eq 0 ]; then
    exit 0
else
    exit 1
fi
```

---

## 6. Performance Profiling & Bottleneck Triage

### Profiler Commands
```bash
# Linux CPU sampling (99 Hz avoids lockstep resonance; dwarf handles omitted frame pointers)
perf record -F 99 -g --call-graph dwarf -- ./build/app
perf report --stdio --no-children -n | head -n 60

# Syscall & I/O latency trace (-ff follow forks, -tt microsecond timestamps, -T syscall duration)
strace -ff -tt -T -e trace=file,network,process -o /tmp/trace.log ./app
strace -c ./app   # aggregate time %, calls, errors per syscall

# Python live production-safe sampling (+ native C frames)
py-spy top --pid <PID>
py-spy record --native -o flame.svg --pid <PID>

# Rust flamegraph (ensure [profile.release] has debug = true; frame pointers aid accuracy)
RUSTFLAGS="-C force-frame-pointers=yes" cargo flamegraph --bin my_service
```

### Distinguishing CPU-Bound vs I/O-Bound vs Lock-Contention
| Signal | CPU-Bound | I/O-Bound | Lock Contention |
|---|---|---|---|
| **CPU Utilization (`top` / `pidstat`)** | 100% of 1 core (or $N \times 100\%$) | Low (<15%) despite high latency | Low-to-moderate CPU, stalls as threads scale |
| **Context Switches (`pidstat -w 1`)** | Mostly involuntary (`nvcswch/s` high, `cswch/s` low) | High voluntary (`cswch/s`) | Very high voluntary `cswch/s` + poor throughput scaling |
| **`strace -c` / `strace -T` Top Calls** | Few syscalls; time spent in user space | `read`, `write`, `epoll_wait`, `poll`, `recvfrom` dominate time | `futex(..., FUTEX_WAIT, ...)` dominates time |
| **Flamegraph / `perf` Signature** | Wide plateau in parser/hash/crypto/loop user frames | Idle wait frames (`epoll_wait`) or off-CPU blocking | Wide frames in `pthread_mutex_lock`, `parking_lot`, `PyEval_RestoreThread` (GIL) |
| **First Fix** | Better algorithm, caching, batching, SIMD/native extension | Async/concurrent I/O, pipelining, DB index, connection pool | Shrink critical sections, shard locks, lock-free reads/immutable snapshots |
