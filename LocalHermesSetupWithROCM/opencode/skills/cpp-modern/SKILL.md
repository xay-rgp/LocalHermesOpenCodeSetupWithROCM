---
name: cpp-modern
description: "Write memory-safe Modern C++20 with RAII, smart pointers, ranges, and zero UB."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [cpp, c++20, raii, stl, sanitizers, concurrency, templates]
    related_skills: [software-architecture, testing-qa, debugging-mastery]
---

# Modern C++20 Engineering & Safety

Memory-safe, warning-free Modern C++20 (`g++ -std=c++20 -Wall -Wextra -Werror -pedantic -Wshadow`) covering RAII, `std::unique_ptr`, `std::string_view`, `std::span`, `std::optional`, `std::variant`, move semantics, `constexpr`, concepts, and thread-safe concurrency verified under ASan/UBSan/TSan.

## When to Use

- Writing, refactoring, or debugging Modern C++20 libraries, headers, and standalone programs (`.hpp`, `.cpp`)
- Eliminating raw `new`/`delete`, dangling references, signed/unsigned conversion warnings, memory leaks, UB, and data races
- Compiling and verifying with `g++ -std=c++20 -Wall -Wextra -Werror -pedantic -Wshadow -fsanitize=address,undefined`

## Core Discipline

1. **Zero raw owning pointers (`new`/`delete`):**
   - Prefer stack values, STL containers (`std::vector`, `std::string`, `std::unordered_map`), and `std::make_unique` / `std::unique_ptr`.
   - Follow the **Rule of Zero** (or Rule of Five when managing a custom resource handle; mark move constructor and move assignment `noexcept`).
2. **Use modern value & view types cleanly:**
   - Pass read-only strings as `std::string_view` and contiguous buffers as `std::span<const T>` (never return a `std::string_view` to a destroyed temporary!).
   - Return `std::optional<T>` instead of sentinel values (`-1`, `nullptr`), and mark query methods `[[nodiscard]]` and `const`.
3. **Zero compiler warnings under `-Wall -Wextra -Werror -pedantic -Wshadow`:**
   - Never shadow member variables or outer locals in constructors/methods/loops (e.g., use `m_cap` or `cap_` for members, `cap` for params).
   - Match signedness (`std::size_t` for container indices/sizes); use `static_cast<...>` explicitly where needed.
   - Always initialize all member variables (prefer in-class default member initializers).
4. **Thread safety & synchronization (TSan-clean):**
   - Protect shared mutable state with `std::mutex` + `std::scoped_lock` / `std::unique_lock` and `std::condition_variable` (always wait with a predicate lambda to guard against spurious wakeups).
   - Prefer `std::jthread` (or explicit `join()` in RAII destructors) so threads are never leaked or terminated abruptly.
5. **Always compile and run with sanitizers before claiming done:**
   - `g++ -std=c++20 -O1 -g -Wall -Wextra -Werror -pedantic -Wshadow -fsanitize=address,undefined <file.cpp> -o /tmp/test_bin && /tmp/test_bin`

## Common Pitfalls

- **`-Wshadow` errors:** Naming a constructor parameter the same as a member variable (`capacity` vs `capacity`) fails under `-Wshadow -Werror`! Suffix private members with `_` (e.g., `capacity_`).
- **Dangling `std::string_view`:** Storing a `std::string_view` pointing to a temporary `std::string` triggers ASan stack-use-after-scope. Own strings with `std::string` inside structs/containers.
- **Unsigned underflow:** Looping `for (std::size_t i = n - 1; i >= 0; --i)` wraps forever; use `for (std::size_t i = n; i-- > 0; )`.
- **Missing `#pragma once` / `#include` headers:** Always start every `.hpp` header with `#pragma once`, and explicitly include `<cstddef>`, `<cstdint>`, `<optional>`, `<string>`, `<string_view>`, `<vector>`, `<memory>`, `<stdexcept>`, `<algorithm>`, `<mutex>`, `<thread>` as needed.
- **Strong exception / atomic batch updates:** When a batch parse or update must be additive AND atomic (no partial mutation on error, rejecting duplicates against existing keys), start from a copy `auto staging = m_store;`, mutate `staging`, and commit with `m_store = std::move(staging);` only after all items succeed.

## Verification

- Compile cleanly with `g++ -std=c++20 -O1 -g -Wall -Wextra -Werror -pedantic -Wshadow -fsanitize=address,undefined` (0 warnings, 0 ASan/UBSan errors).
- For concurrent code, also test with `-fsanitize=thread` (0 TSan data races).

## Course 3 Senior C++20 Pitfalls (Verified)
- **Never Return Non-Copyable Structs by `auto` Value:** A helper returning a shard or lock-holding struct (`struct Shard { mutable std::shared_mutex mtx; ... };`) MUST return `Shard&` / `const Shard&` (or `auto&` / `const auto&`), NEVER `auto` or `const auto` (which deduces by value and fails because `std::shared_mutex` is non-copyable).
