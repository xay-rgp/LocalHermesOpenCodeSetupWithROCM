# C++20/23 RAII, Modern Types, and Concurrency Reference

## 1. Value Categories & Move Semantics (`std::move` vs `std::forward`)

- **Value categories:**
  - **lvalue:** Has identity/address (`x`, `*p`, `vec[0]`); cannot be implicitly moved from.
  - **prvalue:** Pure temporary without identity (`Foo{}`, `make_foo()`); in C++17+, returning/initializing from a prvalue performs **guaranteed copy elision** (constructed directly in caller's storage, no copy/move ctor even required).
  - **xvalue:** Expiring value with identity (`std::move(x)`, `static_cast<T&&>(x)`).
- **`std::move` vs `std::forward`:**
  - `std::move(x)` is an **unconditional cast** to `remove_reference_t<T>&&`. It moves nothing on its own; it enables move overload resolution.
  - `std::forward<T>(x)` is a **conditional cast** used only with forwarding references (`template<class T> void f(T&& x)` or `auto&& x`): preserves lvalue if `T` deduced as `U&`, rvalue if `U`.
  - **Note:** `std::vector<T>&&` in `template<class T>` is an **rvalue reference**, NOT a forwarding reference (only bare `T&&` where `T` is deduced directly on that function template is a forwarding reference).

```cpp
template <typename T, typename... Args>
std::unique_ptr<T> make_logged(Args&&... args) {
    // Forward each arg only once (at last use!)
    return std::make_unique<T>(std::forward<Args>(args)...);
}

std::string build_name() {
    std::string s = "alpha";
    // NEVER `return std::move(s);` — defeats NRVO (Named Return Value Optimization)!
    return s;
}
```

- **Pitfalls:**
  - `const Foo a; Foo b = std::move(a);` silently calls the **copy constructor** (`const Foo&&` does not match `Foo&&`).
  - **Moved-from state:** Standard types remain in a *valid, unspecified* state (safe to destroy or reassign, e.g. `s = "next";`). Do not read values out of moved-from objects without resetting them.

## 2. Rule of Zero & Rule of Five

- **Rule of Zero (99% of classes):** Compose RAII members (`std::string`, `std::vector`, `std::unique_ptr`) and declare **no** custom destructor, copy, or move operations.
- **Destructor suppression trap:** Declaring *any* user-declared destructor—even `~Widget() = default;`—**suppresses automatic generation of move constructor and move assignment**!
- **Rule of Five (resource-owning wrappers only):** If you manage a raw OS handle/C pointer (`FILE*`, socket fd), define all 5 (`~T`, copy ctor, copy assign, move ctor, move assign) or delete copy operations for unique handles. Always mark move operations `noexcept` so `std::vector` moves instead of copying during reallocation!

```cpp
class UniqueFd {
    int fd_ = -1;
public:
    explicit UniqueFd(int fd = -1) noexcept : fd_(fd) {}
    ~UniqueFd() noexcept { reset(); }

    UniqueFd(const UniqueFd&) = delete;
    UniqueFd& operator=(const UniqueFd&) = delete;

    UniqueFd(UniqueFd&& other) noexcept
        : fd_(std::exchange(other.fd_, -1)) {}

    UniqueFd& operator=(UniqueFd&& other) noexcept {
        if (this != &other) {
            reset();
            fd_ = std::exchange(other.fd_, -1);
        }
        return *this;
    }

    void reset(int new_fd = -1) noexcept {
        if (fd_ >= 0) ::close(fd_);
        fd_ = new_fd;
    }
    int get() const noexcept { return fd_; }
};
```

## 3. Smart Pointers & Custom Deleters

| Pointer | Ownership | Cycle Safe? | Overhead |
|---|---|---|---|
| `std::unique_ptr<T, D>` | Exclusive | Yes | Zero (with stateless functor `D`) |
| `std::shared_ptr<T>` | Shared (atomic refcount) | Needs `weak_ptr` | Control block + atomic inc/dec |
| `std::weak_ptr<T>` | Non-owning observer | Breaks cycles | Check via `.lock()` |

- **Prefer `std::make_unique` / `std::make_shared`** over bare `new`: avoids leak risk on interleaved evaluation and combines object + control block into one allocation for `make_shared`. (Caveat: `make_shared` keeps the combined block allocated until all `weak_ptr`s expire too.)
- **Zero-overhead C resource deleters:** Use a stateless functor struct, NOT a function pointer `void(*)(FILE*)` (function pointers double `sizeof(unique_ptr)`):

```cpp
struct FileCloser {
    void operator()(std::FILE* f) const noexcept {
        if (f) std::fclose(f);
    }
};
using UniqueFile = std::unique_ptr<std::FILE, FileCloser>;
static_assert(sizeof(UniqueFile) == sizeof(std::FILE*));
```

- **Safe `weak_ptr` access:** Never check `if (!wp.expired()) use(wp.lock())` (TOCTOU race across threads). Always promote atomically: `if (auto sp = wp.lock()) { /* use *sp */ }`.
- **Base classes:** Polymorphic bases deleted via base pointer MUST have `virtual ~Base() = default;`.

## 4. Vocabulary & View Types (`span`, `string_view`, `optional`, `variant`, `expected`)

- **`std::span<const T>` / `std::string_view`:** Pass by value (`{ptr, len}`). **Never store a view pointing to a temporary** (`std::string_view sv = make_str();` -> instant dangling UB). `std::string_view` is NOT guaranteed NUL-terminated; never pass `.data()` to C APIs expecting `\0`.
- **`std::optional<T>`:** Stack-allocated nullable value. `*opt` does **not** check presence (UB when empty); use `if (opt)` or `.value_or(fallback)`. `std::optional<T&>` is ill-formed in C++20; use non-owning `T*` or `std::reference_wrapper<T>`.
- **`std::variant<Ts...>` + `std::visit`:** Type-safe tagged union. Use `std::monostate` as the first type if an alternative isn't default-constructible.

```cpp
template <class... Ts> struct Overloaded : Ts... { using Ts::operator()...; };
template <class... Ts> Overloaded(Ts...) -> Overloaded<Ts...>; // C++17 CTAD helper (optional in C++20)

using Event = std::variant<int, std::string>;
void handle(const Event& ev) {
    std::visit(Overloaded{
        [](int code) { /* ... */ },
        [](const std::string& msg) { /* ... */ },
    }, ev);
}
```

- **`std::expected<T, E>` (C++23 `<expected>`):** Non-exceptional typed error return with `.and_then()`, `.transform()`, `.or_else()`. In C++20, use `std::variant` or a lightweight `tl::expected` equivalent at error boundaries.

## 5. C++20 Concepts & Ranges

- **Concepts (`<concepts>`):** Constrain templates cleanly at the interface, giving one-line diagnostics instead of pages of SFINAE tracebacks.

```cpp
#include <concepts>
#include <ranges>
#include <string>

template <typename T>
concept Serializable = requires(const T& v) {
    { v.to_bytes() } -> std::convertible_to<std::string>;
};

template <Serializable T>
void send(const T& item) {
    auto payload = item.to_bytes();
    (void)payload;
}

// Ranges: lazy pipeline + projections
struct Task { int priority; bool active; };

int top_active_priority(std::span<const Task> tasks) {
    auto active = tasks | std::views::filter(&Task::active);
    auto it = std::ranges::max_element(active, {}, &Task::priority);
    return (it != std::ranges::end(active)) ? it->priority : -1;
}
```

- **Ranges pitfalls:**
  - Algorithms return `std::ranges::dangling` if given an rvalue temporary container (`std::ranges::max_element(get_vec())` refuses to dereference).
  - In C++20, `views::filter` caches `begin()` inside the view object, so iterating a `const` `filter_view` fails to compile—keep views non-`const`.
  - Don't construct views over temporary ranges (`auto v = make_vec() | views::take(3);` -> dangling!).

## 6. `std::atomic`, Memory Ordering, and the ABA Problem

Every shared non-atomic location accessed concurrently with at least one writer is a **data race (UB)** in C++.

| Memory Order | Guarantee | Primary Use |
|---|---|---|
| `relaxed` | Atomicity + single-var modification order only; no cross-var ordering | Metrics counters, `shared_ptr` refcount increment |
| `release` / `acquire` | `release` store **synchronizes-with** `acquire` load reading it: prior non-atomic writes become visible | Publishing initialized structs, SPSC flags, mutex unlock/lock |
| `acq_rel` | Both `acquire` and `release` on read-modify-write | Lock-free CAS, `shared_ptr` refcount decrement |
| `seq_cst` (default) | `acq_rel` + single total order across all `seq_cst` ops | Multi-variable Dekker/Peterson protocols (slower on ARM64/POWER) |

```cpp
#include <atomic>
#include <string>

struct PublishSlot {
    std::string payload;
    std::atomic<bool> ready{false};

    void publish(std::string data) {
        payload = std::move(data);                       // non-atomic write BEFORE release
        ready.store(true, std::memory_order_release);    // synchronizes-with acquire below
    }

    bool try_consume(std::string& out) {
        if (!ready.load(std::memory_order_acquire)) return false;
        out = payload;                                   // guaranteed to see published data
        return true;
    }
};
```

- **CAS loop (`compare_exchange_weak` vs `_strong`):** Use `weak` inside `while` loops (cheaper on LL/SC architectures like ARM where spurious failure occurs); use `strong` for single-shot checks.
- **ABA Problem:** In lock-free stacks/queues using `head.compare_exchange_weak(old_head, old_head->next)`: Thread 1 reads `old_head = A` and `next = B`, then pauses; Thread 2 pops `A`, pops `B`, reallocates/reuses `A` and pushes `A` back as head; Thread 1's CAS sees `head == A` and succeeds, pointing `head` at freed `B`!
  - **Mitigations:** Pack a monotonic generation tag (`struct TaggedPtr { Node* ptr; uint64_t tag; };`, requires `-mcx16` on x86-64 for lock-free 16-byte CAS—verify `static_assert(std::atomic<TaggedPtr>::is_always_lock_free)`), epoch-based reclamation, hazard pointers, or use a mutex unless lock-free latency is measured necessary.

## 7. `std::scoped_lock` & Condition Variables

- **Deadlock-free multi-locking:** `std::scoped_lock lock(m1, m2);` acquires both mutexes without lock-order inversion. Never lock two mutexes with separate `lock_guard`s in inconsistent orders.
- **Condition variable rules:**
  - Always use `std::unique_lock` with `std::condition_variable`.
  - Always pass a **predicate** (`cv.wait(lk, pred)`) to guard against **spurious wakeups** and already-satisfied conditions (**lost wakeups**).
  - Mutate the condition variable's state **while holding the mutex** before calling `notify_one()` / `notify_all()`.

```cpp
#include <condition_variable>
#include <mutex>
#include <queue>
#include <stop_token>

template <typename T>
class BoundedQueue {
    std::mutex mu_;
    std::condition_variable_any cv_;
    std::queue<T> q_;
public:
    void push(T item) {
        {
            std::scoped_lock lk(mu_);
            q_.push(std::move(item));
        }
        cv_.notify_one();
    }

    // C++20 cooperative cancellation via std::stop_token (pairs with std::jthread)
    bool pop(std::stop_token st, T& out) {
        std::unique_lock lk(mu_);
        if (!cv_.wait(lk, st, [&] { return !q_.empty(); })) return false; // stop requested
        out = std::move(q_.front());
        q_.pop();
        return true;
    }
};
```

## 8. Modern Target-Based CMake & Sanitizers

Never use global `include_directories()`, `link_libraries()`, or `CMAKE_CXX_FLAGS` overrides when target properties suffice.

```cmake
cmake_minimum_required(VERSION 3.22)
project(app LANGUAGES CXX)

add_library(core src/core.cpp)
target_include_directories(core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_compile_features(core PUBLIC cxx_std_20)
target_compile_options(core PRIVATE
    $<$<CXX_COMPILER_ID:GNU,Clang,AppleClang>:-Wall -Wextra -Wpedantic -Wshadow -Wconversion>
    $<$<CXX_COMPILER_ID:MSVC>:/W4 /permissive->
)

add_executable(app_tests tests/main.cpp)
target_link_libraries(app_tests PRIVATE core)
enable_testing()
add_test(NAME unit COMMAND app_tests)
```

### Sanitizer Matrix (Use Separate Build Directories!)

| Build Dir | Flags | Catches | Constraints |
|---|---|---|---|
| `build-asan` | `-O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined` | OOB, UAF, leaks, UB, misalignment | Incompatible with TSan & MSan |
| `build-tsan` | `-O1 -g -fno-omit-frame-pointer -fsanitize=thread` | Data races, lock-order inversions | Incompatible with ASan/MSan; 64-bit |
| `build-msan` | `-O1 -g -fno-omit-frame-pointer -fsanitize=memory -fsanitize-memory-track-origins` | Uninitialized reads | Clang/Linux only; deps/libc++ must also be MSan-built |

```bash
# ASan + UBSan (fail fast with stack traces)
cmake -B build-asan -DCMAKE_BUILD_TYPE=Debug \
  -DCMAKE_CXX_FLAGS="-O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined"
cmake --build build-asan
UBSAN_OPTIONS=print_stacktrace=1:halt_on_error=1 ctest --test-dir build-asan --output-on-failure

# TSan (dedicated concurrent test pass)
cmake -B build-tsan -DCMAKE_BUILD_TYPE=Debug \
  -DCMAKE_CXX_FLAGS="-O1 -g -fno-omit-frame-pointer -fsanitize=thread"
cmake --build build-tsan && ctest --test-dir build-tsan --output-on-failure
```
