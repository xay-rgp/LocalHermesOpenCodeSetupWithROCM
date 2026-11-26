---
name: cpp-c-development
description: "Write UB-free C and modern C++20 with RAII and sanitizers."
version: 1.0.0
author: Xay, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [c, cpp, raii, memory-management, sanitizers, cmake, systems]
    related_skills: [rust-development, debugging-mastery, linux-development, algorithms-cs]
---

# C and C++ Development

Safe, high-performance C11/C17 and modern C++20/23 engineering focused on deterministic resource management (RAII), eliminating undefined behavior, concurrency, and sanitizer-verified builds.

## When to Use

- Writing, reviewing, optimizing, or debugging C or C++ codebases, libraries, or CMake builds
- Diagnosing segfaults, use-after-free, buffer overflows, data races, template errors, or ABI/linker failures
- Migrating legacy raw-pointer C++ to RAII, smart pointers, `std::span`, and C++20 concepts
- Don't use for: managed-memory languages when no C/C++ FFI is involved

## Core Discipline

1. **Zero undefined behavior (UB).** Compilers optimize assuming UB never occurs — signed overflow, out-of-bounds access, uninitialized reads, strict-aliasing violations, and data races silently break unrelated code.
2. **In C++, obey RAII and the Rule of Zero.** Own heap memory with `std::unique_ptr`, containers (`std::vector`, `std::string`), and value semantics; write custom destructor/copy/move ONLY in dedicated resource-wrapper classes (Rule of Five). Never call bare `new`/`delete` in application code.
3. **In C, make ownership and lifetimes explicit in every signature.** Pass `(ptr, len)` pairs together, initialize pointers to `NULL`, use a single `goto cleanup;` exit path for multi-resource functions, and check every syscall/allocation return value.
4. **Compile with strict warnings and sanitizers during development.** Always build dev/test targets with `-Wall -Wextra -Wpedantic -Wshadow -Wconversion` and test under `-fsanitize=address,undefined` (and `-fsanitize=thread` for concurrent code).
5. **Separate interfaces cleanly.** Put minimal includes in headers (use forward declarations where possible), mark single-argument constructors `explicit`, and prefer `constexpr` / `const` everywhere.

## Quick Reference

| Task | C Idiom | Modern C++20/23 Idiom |
|---|---|---|
| Non-owning view | `(const T* ptr, size_t len)` | `std::span<const T>`, `std::string_view` |
| Unique ownership | `malloc` + `goto cleanup` + `free` | `std::unique_ptr<T>` + `std::make_unique` |
| Fallible return | `int` status + out-param / `errno` | `std::expected<T, E>` (C++23) / `std::optional<T>` |
| Type-safe union | Tagged `struct { enum tag; union ...; }` | `std::variant<Ts...>` + `std::visit` |
| Type punning | `memcpy(&dst, &src, sizeof dst)` | `std::bit_cast<Dst>(src)` |
| Thread-safe flag/counter | `<stdatomic.h>` `_Atomic` | `std::atomic<T>` with explicit memory order |
| Mutex locking | `pthread_mutex_lock` + cleanup | `std::scoped_lock lock(m1, m2);` (deadlock-free) |

## Deep References

Load on demand with `skill_view("cpp-c-development", file_path="...")`:
- `references/c-systems-and-ub.md` — C memory layouts, alignment/padding, strict aliasing, pointer provenance, arena allocators, safe buffer APIs, POSIX error & signal handling, header/ABI hygiene.
- `references/cpp20-raii-concurrency.md` — Value categories & move semantics, perfect forwarding, smart pointer ownership graphs, C++20 concepts & ranges, `std::atomic` memory ordering, lock-free hazards, CMake & sanitizer presets.

## Implementation Procedure

1. **Enable warnings and sanitizers first.** Configure debug builds with `-O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined` before implementing or debugging. Completion criterion: build target compiles with 0 warnings under `-Wall -Wextra`.
2. **Design ownership and error boundaries.** Decide who owns every allocation and how errors cross module boundaries (never throw C++ exceptions across `extern "C"` boundaries). Completion criterion: every heap/OS resource has a deterministic release path on both success and failure.
3. **Implement and test edge cases.** Test zero-length buffers, max/min integer bounds, null inputs, self-assignment, and moved-from objects. Completion criterion: full test suite passes under ASan + UBSan with zero findings.
4. **Verify concurrency under TSan.** For multithreaded code, run a dedicated `-fsanitize=thread` build (TSan cannot be combined with ASan in one binary). Completion criterion: zero data races or lock-order inversions reported.

## Common Pitfalls

- **Dangling `std::string_view` or `std::span`:** Returning a `string_view` pointing to a temporary `std::string` is immediate use-after-free. Views never extend lifetime.
- **Strict aliasing violation via pointer casts:** `*(uint32_t*)&float_val` is UB. Always use `memcpy` (C) or `std::bit_cast` (C++20); the compiler optimizes both to a single register move.
- **Signed integer overflow:** `int` overflow is UB in C/C++, allowing compilers to delete bounds checks like `x + 1 > x`. Check before adding (`a > INT_MAX - b`) or use unsigned / `__builtin_add_overflow`.
- **`std::vector` iterator/reference invalidation:** `push_back`/`emplace_back` can reallocate and invalidate ALL pointers, references, and iterators into the vector. Never pass `&vec[0]` into `vec.push_back(...)` without reserving capacity first.
- **`std::shared_ptr` reference cycles:** Two objects holding `shared_ptr` to each other leak permanently. Break back-edges with `std::weak_ptr`.
- **Virtual destructor omission:** Deleting a derived object through a base pointer without `virtual ~Base() = default;` is UB.
- **Unchecked `realloc` leak:** `ptr = realloc(ptr, n)` leaks the original block if `realloc` returns `NULL`. Always assign to a temporary: `void *tmp = realloc(ptr, n); if (!tmp) { ... } ptr = tmp;`.
- **Static initialization order fiasco (C++):** Global objects across translation units initialize in unspecified order. Use function-local statics (Meyers' singleton) or `constinit`.
- **Concurrent `std::vector::push_back` after `reserve()`:** `reserve()` prevents reallocation, NOT data races — concurrent writers still race on internal size pointers (instant UB / TSan failure). Always protect shared containers with `std::mutex` or give each thread a thread-local buffer and merge after `join()`.

## Verification

- Build & test with ASan + UBSan: `terminal(command="cmake -B build-asan -DCMAKE_BUILD_TYPE=Debug -DCMAKE_CXX_FLAGS='-Wall -Wextra -Wpedantic -fsanitize=address,undefined -fno-omit-frame-pointer' && cmake --build build-asan && ctest --test-dir build-asan --output-on-failure")`.
- For multithreaded targets, also build and test with `-fsanitize=thread`.
- Verify zero memory leaks reported by LeakSanitizer/Valgrind on exit.
