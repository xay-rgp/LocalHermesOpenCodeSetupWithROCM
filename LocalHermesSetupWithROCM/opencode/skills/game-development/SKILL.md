---
name: game-development
description: Senior game engine and systems engineering patterns across C++20, Python, and HTML5 Canvas (fixed-timestep loops, spatial hashing, ECS generational handles, admissible A* pathfinding, lock-free/double-buffered render queues, and input buffering).
---

# Senior Game Development Engineering

## Fixed-Timestep Simulation Loop (C++20)
- **Spiral-of-Death Guard:** Always clamp incoming `raw_frame_dt` to `[0.0, max_frame_dt]` (e.g., `0.25s`) before adding to the physics accumulator, and report `was_clamped` accurately.
- **Deterministic Accumulator & Render Interpolation:** Step the simulation while `accumulator >= fixed_dt`, passing `fixed_dt` to a templated `StepFn&&` (zero heap allocation, supports move-only callables). Compute `alpha = accumulator / fixed_dt` in `[0.0, 1.0)` for `lerp(prev, curr, alpha)`.
- **C++20 Accessor Qualifiers:** Always place `const noexcept` *after* the parameter list (`double alpha() const noexcept`), never before the return type.

## A* Grid Pathfinding (Python)
- **Admissible Heuristics:** Use **Octile** distance (`max(dr, dc) + (sqrt(2) - 1) * min(dr, dc)`) when diagonal moves (`cost = sqrt(2)`) are allowed, and **Manhattan** (`dr + dc`) for 4-way movement. Never over-weight heuristics when optimal paths are required.
- **No Diagonal Corner-Cutting:** Before taking a diagonal step `(dr, dc)` where `dr != 0 and dc != 0`, verify BOTH orthogonal neighbors `(r + dr, c)` and `(r, c + dc)` are passable.
- **Relaxation & Stale Heap Entries:** Never mark nodes visited on push; relax whenever `tentative_g < g_score.get(nbr, inf)` and skip stale popped heap entries.

## Double-Buffered Render Command Queue (C++20, TSan-Clean)
- **Lock Scope Minimization:** Protect only the back-buffer `push_back` and the O(1) `swap` in `swap_and_drain()` under `std::mutex`; perform `std::stable_sort` by `(layer, sort_key, mesh_id)` *outside* the lock on the drained front buffer so producer simulation threads are never blocked during sorting.
- **Acquire/Release Frame Counter:** Increment `std::atomic<std::uint64_t> frame_counter` with `std::memory_order_release` on swap and read via `std::memory_order_acquire`.

## HTML5 Canvas GameClock & Input Buffering (JS)
- **Jump Buffer & Coyote Time (`InputBuffer`):** Maintain two countdown timers (`jumpBufferTimer` set on `pressJump()`, `coyoteTimer` reset to `coyoteTimeSec` while grounded and decremented when airborne). `consumeJump()` triggers and zeroes both timers when `jumpBufferTimer > 0 && coyoteTimer > 0`.
- **Headless-Testable Engine Modules:** Guard DOM/Canvas bootstrapping with `if (typeof document !== "undefined")` and export pure simulation classes (`GameClock`, `InputBuffer`) on `globalThis` so Node.js tests can verify game-loop math deterministically.
