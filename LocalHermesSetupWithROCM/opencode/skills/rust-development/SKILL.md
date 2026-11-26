---
name: rust-development
description: "Build safe, fast Rust with ownership, traits, and Tokio."
version: 1.0.0
author: Xay, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [rust, ownership, lifetimes, traits, tokio, systems, memory-safety]
    related_skills: [cpp-c-development, debugging-mastery, testing-qa, software-architecture]
---

# Rust Development

Idiomatic, memory-safe, zero-cost Rust engineering across ownership, lifetimes, traits, error handling, Tokio async, concurrency, and `unsafe` soundness.

## When to Use

- Writing, refactoring, optimizing, or debugging Rust binaries, libraries, or FFI bindings
- Resolving borrow-checker, lifetime, `Send`/`Sync`, or async `Pin` compiler errors
- Designing trait hierarchies, error types, concurrent state machines, or `unsafe` abstractions
- Don't use for: non-Rust projects

## Core Discipline

1. **Design around ownership, not against the borrow checker.** Prefer owned values (`T`) or short-lived borrows (`&T`, `&mut T`) over `Rc<RefCell<T>>` or `Arc<Mutex<T>>` graphs. Use indices/arenas for cyclic or graph structures.
2. **Make illegal states unrepresentable with enums and typestates.** Encode state transitions in enums (`enum Conn { Disconnected, Connected(Socket) }`) or zero-sized phantom typestates so invalid calls fail at compile time.
3. **Never `.unwrap()` or `.expect()` on untrusted or runtime-fallible data in production paths.** Propagate errors with `?`, use `thiserror` in libraries for structured enums, and `anyhow` in binaries for rich context (`.context("...")`).
4. **Minimize and document every `unsafe` block.** Encapsulate `unsafe` behind a safe API boundary and write an explicit `// SAFETY: ...` comment proving every precondition.
5. **Avoid holding locks across `.await`.** Never hold a `std::sync::MutexGuard` across an `.await` point (deadlocks executor threads). Clone/extract data first, drop the guard, then `.await`.

## Quick Reference

| Need | Idiomatic Rust Choice | Notes |
|---|---|---|
| Library errors | `thiserror::Error` enum | Callers can match variants |
| Binary/CLI errors | `anyhow::Result<T>` + `.with_context(...)` | Fast ergonomic propagation |
| Single-thread shared mutability | `Cell<T>` (Copy) / `RefCell<T>` | Avoid if restructuring ownership works |
| Multi-thread shared state | `Arc<RwLock<T>>` or message passing (`mpsc`) | Prefer channels over coarse shared locks |
| One-time lazy init | `std::sync::OnceLock` / `LazyLock` | Stdlib since Rust 1.70/1.80 |
| Static vs dynamic dispatch | `impl Trait` / generics vs `Box<dyn Trait>` | Use `dyn` for heterogeneous collections or compile-time reduction |
| Slice/string parameters | `&[T]`, `&str`, `&Path` | Never take `&Vec<T>` or `&String` in public APIs |

## Deep References

Load on demand with `skill_view("rust-development", file_path="...")`:
- `references/ownership-lifetimes-traits.md` — Borrowing rules, NLL, lifetime elision, HRTB (`for<'a>`), variance, interior mutability, trait object safety, `Cow<'a, T>`, typestate pattern.
- `references/async-errors-unsafe.md` — Tokio runtime & blocking pools, `select!` cancellation safety, `Pin`/`Unpin`, structured error design, `unsafe` invariants, FFI, Miri, Cargo/Clippy profiling.

## Implementation Procedure

1. **Model domain types first.** Define structs, enums, and error types before writing functions. Completion criterion: `cargo check` compiles type definitions cleanly.
2. **Write minimal safe implementation.** Keep borrows narrow, accept borrowed slices (`&str`, `&[T]`), and avoid premature `.clone()` unless ownership semantics genuinely require it. Completion criterion: `cargo clippy --all-targets -- -D warnings` passes with 0 warnings.
3. **Test behavior, edge cases, and concurrency.** Put unit tests in `#[cfg(test)] mod tests` and public-API integration tests in `tests/`. Completion criterion: `cargo test` passes completely, including doc-tests.
4. **Audit `unsafe` and performance.** Run `cargo +nightly miri test` when `unsafe` code exists, and benchmark with `criterion` before micro-optimizing. Completion criterion: every `unsafe` block has a verified `// SAFETY:` invariant.

## Common Pitfalls

- **Fighting lifetimes with `'static` everywhere:** Adding `'static` or cloning everything hides design flaws. Often splitting a struct into smaller borrowed fields fixes disjoint-field borrow conflicts cleanly.
- **Blocking the Tokio runtime:** Calling `std::thread::sleep`, synchronous file/DB I/O, or heavy CPU loops inside an `async fn` starves worker threads. Use `tokio::task::spawn_blocking` (note: closures must be `'static`, so convert borrowed `&[u8]`/`&str` to owned `to_vec()`/`to_owned()` first and map `JoinError`) or a dedicated Rayon pool.
- **Cancellation unsafety & EOF spin in `tokio::select!`:** If a future holds buffered state (like `AsyncReadExt::read_exact` or multi-step protocols) and loses a `select!` race, dropping it discards partial progress. Use cancel-safe `read_buf(&mut bytes_mut)` (`bytes::BytesMut` + `bytes::Buf`), ALWAYS check `if n == 0 { break; }` to avoid an infinite 100%-CPU spin on peer EOF, drain frames in a `while` loop, and cap frame lengths against OOM.
- **Integer overflow divergence:** Debug builds panic on overflow; release builds wrap silently. Use `checked_add`, `saturating_sub`, or `wrapping_mul` whenever bounds matter.
- **Lock poisoning & panic safety:** `std::sync::Mutex::lock()` returns `Err(PoisonError)` if a prior holder panicked. Decide deliberately whether to propagate, recover, or use `parking_lot::Mutex` with clear invariants.
- **Recursive `async fn`:** Direct recursion in `async fn` has infinite future size; box the recursive call (`Box::pin(...)`).
- **Test-only helpers outside `#[cfg(test)]`:** Placing private helper functions outside `#[cfg(test)] mod tests` causes `dead_code` warnings under `cargo clippy -- -D warnings` in non-test builds. Keep test helpers inside `mod tests`.
- **Clippy idiomatic combinators:** Prefer `.map(String::as_str)` over `.map(|s| s.as_str())`, `.ok_or_else(...)` over verbose `match ... { Some(x) => x, None => return Err(...) }`, `.is_empty()` over `.len() == 0`, `.max()` directly when `Ord` is derived, and NEVER write redundant `.map(|v| v)` (`clippy::map_identity`).
- **Returning `impl Iterator` with captured local params:** Any closure inside a returned `impl Iterator` that uses a local `Copy` parameter (e.g., `now_s: u64`) MUST use `move |...|` so the iterator owns `now_s` instead of borrowing the local stack frame (otherwise `rustc` rejects with E0373: closure may outlive current function).
- **`Display::fmt` exact signature:** Always write `fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result` — NEVER `f: &mut fmt::Result` and NEVER `-> fmt::Result<()>` (`std::fmt::Result` takes zero generic parameters). Also in tests, never write `assert_eq!(res.unwrap(), Ok(()))` (`unwrap()` already extracts `()`).
- **Write code to files explicitly:** Never print a Rust solution only in chat when asked to create a file — always invoke `write_file` and confirm the file exists on disk. When asserting `Result<MyStruct, MyError>` with `assert_eq!` in tests, ensure `MyStruct` derives `Debug, PartialEq, Eq` (or check `.unwrap_err()`), and scan the final file for stray glued tokens like `int}`, `>int`, `placeholder`, or literal `\n`.

## Verification

- Run `terminal(command="cargo fmt --check && cargo clippy --all-targets -- -D warnings && cargo test")`.
- For release builds, verify with `terminal(command="cargo test --release")` to catch debug-only assumption bugs (e.g., overflow behavior).
- If `unsafe` exists, run `terminal(command="cargo +nightly miri test")` when Miri is available.

## Course 3 Senior Rust Pitfalls (Verified)
- **`&str` Byte Indexing:** `&str` does NOT implement `Iterator` — never call `s.enumerate()`. Always use `s.char_indices()` for `(byte_idx, char)` pairs when slicing `&str`.
- **Single-Character Literals Only:** Rust `char` literals (`'t'`, `'\n'`) hold exactly one Unicode scalar value; double-check every `match` arm for multi-char typos.
- **Cursor Accounting in Zero-Copy Parsers:** When splitting `remainder` with `split_once('=')`, advance `self.pos` by `key.len() + 1 + value_len`, not just `value_len`.
- **Lazy `Cow::Borrowed` -> `Cow::Owned`:** Only allocate `String` when an escape sequence is actually encountered; otherwise return `Cow::Borrowed(&val_part[1..end])`.
- **Avoid `&mut self` Helper Calls While Borrowing a Field (`E0499`):** Never call `self.next_tick()` while `self.map.get_mut(...)` or `self.map.insert(...)` holds a mutable borrow of `self.map`. Precompute `let tick = self.next_tick();` BEFORE borrowing `self.map`, or mutate `self.counter` directly as a disjoint field.
- **Returning `Option<&V>` After Conditional Removal (NLL Borrow Checker):** Do NOT call `self.map.remove(key)` inside `if let Some(entry) = self.map.get_mut(key)` when another branch returns `Some(&entry.value)`. Instead, check expiration with `if self.map.get(key).is_some_and(|e| now >= e.expires_at) { self.map.remove(key); return None; }` first, then do `self.map.get_mut(key).map(...)`.
- **Non-`Clone` `Vec<Option<T>>` Initialization & `capacity == 0` Guards:** Never use `vec![None; cap]` or `buf.resize(cap, None)` on generic `T` without `T: Clone`; use `for _ in 0..cap { buf.push(None); }` instead, and always guard `if self.is_empty() { return None; }` in `peek()` before indexing `buf[head]`.
- **Byte-Level ASCII Validation in Zero-Copy Parsers:** Inspect `for &b in line.as_bytes()` (NEVER `c as u8` on `char`, which silently truncates multi-byte UTF-8 code points!) and strip a single trailing `\r` via `raw.strip_suffix('\r').unwrap_or(raw)` before control-char checks.
- **Rust `ThreadPool` Deadlock & Serialization Prevention:** In worker loops receiving from `Arc<Mutex<mpsc::Receiver<Job>>>`, ALWAYS drop the `MutexGuard` in an inner scope (`let job = { rx.lock().unwrap().recv() };`) BEFORE executing `job()`, otherwise all workers serialize behind the mutex and deadlock on a `Barrier`. In `impl Drop`, ALWAYS call `drop(self.sender.take())` BEFORE `handle.join()`, so workers observe `Err(RecvError)` and exit cleanly.
- **RFC 8259 JSON Number Validation:** After optional leading `-`, if the first digit is `'0'` and the next byte is another ASCII digit (`'0'..='9'`), reject as an invalid leading zero (while still allowing `0`, `0.5`, `0e1`). Always slice `&self.input[start..self.cursor]` (NOT `&self.input[start..]`) before `.parse::<f64>()`.
- **Generational `Slab<T>` Intrusive Free-List:** On `insert()`, pop `idx` from `self.free_head`, swap `SlotData::Occupied(value)` in via `std::mem::replace`, and restore `self.free_head = next_free` from the replaced `SlotData::Vacant(next_free)`. On `remove(handle)`, verify `slot.generation == handle.generation && matches!(slot.data, SlotData::Occupied(_))`, swap in `SlotData::Vacant(self.free_head)`, set `self.free_head = Some(handle.index)`, and bump `slot.generation = slot.generation.wrapping_add(1)` for ABA safety. Always place `impl<T> Default for Slab<T>` at top level (outside `impl<T> Slab<T> { ... }`).
