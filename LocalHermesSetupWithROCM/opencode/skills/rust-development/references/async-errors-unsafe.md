# Rust Async, Error Handling, and Unsafe Reference

## 1. Structured Error Design (`thiserror` vs `anyhow`)

### Library Crates — Typed Enum with `thiserror`
```rust
use thiserror::Error;

#[derive(Debug, Error)]
pub enum StorageError {
    #[error("record {id} not found")]
    NotFound { id: u64 },
    #[error("corrupt payload at offset {offset}")]
    Corrupt { offset: usize },
    #[error("i/o failure")]
    Io(#[from] std::io::Error),
}
```
- Preserve `#[source]` / `#[from]` so callers and error reporters can walk the full causal chain.
- Never `#[from]` indiscriminately if two variants wrap the same error type or if losing domain context hurts callers — map explicitly with `.map_err(|e| StorageError::ReadConfig { path, source: e })`.

### Application Crates — `anyhow`
```rust
use anyhow::{Context, Result};

fn load_config(path: &std::path::Path) -> Result<Config> {
    let raw = std::fs::read_to_string(path)
        .with_context(|| format!("failed to read config at {}", path.display()))?;
    toml::from_str(&raw).context("invalid TOML syntax")
}
```
Use `.with_context(|| ...)` (lazy closure) instead of `.context(format!(...))` so the error string allocates ONLY on failure.

## 2. Tokio Async & Concurrency Mastery

### `Send`, `Sync`, and Multi-Threaded Executors
- `tokio::spawn` requires `Future + Send + 'static`.
- A future is `!Send` if a `!Send` value (e.g., `Rc`, `RefCell`, `std::sync::MutexGuard`) is **live across an `.await` point**.
- **Fix:** Scope non-`Send` values and `std::sync::MutexGuard` inside `{ ... }` before `.await`:

```rust
let snapshot = {
    let guard = state.lock().expect("poisoned");
    guard.clone()
}; // guard dropped here!
send_over_network(&snapshot).await?;
```

### Cancellation Safety in `tokio::select!`
When one branch of `tokio::select!` completes, all other branches are **dropped**.
- **Cancel-safe:** `mpsc::Receiver::recv`, `broadcast::Receiver::recv`, `tokio::time::sleep`, `TcpListener::accept`, `AsyncReadExt::read_buf` (with external `BytesMut`).
- **NOT cancel-safe:** `AsyncReadExt::read_exact`, `AsyncWriteExt::write_all`, multi-step `async fn` that mutates state mid-way.
- **Pattern:** Keep the non-cancel-safe future pinned outside the loop, or pass an explicit buffer that retains partial bytes across iterations.

### Structured Task Management & Graceful Shutdown
- Use `tokio::task::JoinSet` to spawn bounded dynamic tasks and abort all remaining tasks automatically when the `JoinSet` drops.
- Propagate shutdown with `tokio_util::sync::CancellationToken` or `tokio::sync::watch::channel(false)`.
- Offload blocking disk/SQLite/CPU work with `tokio::task::spawn_blocking`. Never call `std::thread::sleep` inside an async task.

### Channels Selection
- `oneshot`: single request/response reply.
- `mpsc` (bounded!): work queues with backpressure — avoid `unbounded_channel` in services accepting external traffic.
- `watch`: single latest value (config reload, shutdown signal).
- `broadcast`: multi-consumer fan-out (watch for `RecvError::Lagged`).

## 3. `unsafe` Rust, Soundness, and FFI

`unsafe` unlocks exactly 5 superpowers: dereferencing raw pointers, calling `unsafe fn`/FFI, accessing mutable statics, implementing `unsafe trait` (`Send`/`Sync`), and reading union fields. It does **NOT** disable the borrow checker.

### Mandatory `unsafe` Discipline
1. Never construct `&mut T` aliasing any other live `&T` or `&mut T` (instant Stacked Borrows / Tree Borrows UB even if never written!).
2. Never create unaligned, null, or dangling references (`&T` must always be valid even if unread). Use raw pointers (`*const T`, `*mut T`) and `ptr::read_unaligned` / `MaybeUninit<T>` instead.
3. Wrap every `unsafe` block in a small safe abstraction and write `// SAFETY:` explaining why the caller/invariant guarantees soundness.
4. Test `unsafe` code with **Miri**: `cargo +nightly miri test` catches aliasing UB, uninitialized reads, out-of-bounds pointer arithmetic, and leaks.

### FFI Boundaries (`extern "C"`)
- **Unwinding across `extern "C"` is UB** (in Rust <1.81 / non-`-unwind` ABI): wrap Rust callbacks called from C in `std::panic::catch_unwind` and return an error code.
- Use `#[repr(C)]` on structs shared with C and `CStr`/`CString` for null-terminated strings.
- Never `free()` Rust-allocated memory with C `free()` or vice versa; expose an explicit `my_lib_free(ptr)` matching the allocator that created it.

## 4. Tooling & Performance Checklist
- Lint strictly: `cargo clippy --all-targets --all-features -- -D warnings`
- Release profiling symbols: set `debug = true` in `[profile.release]` when profiling with `perf` / `flamegraph`.
- Avoid `Vec` reallocations with `Vec::with_capacity(n)`, reuse scratch `String`/`Vec` buffers via `.clear()` inside hot loops, and measure with `criterion` before optimizing.
