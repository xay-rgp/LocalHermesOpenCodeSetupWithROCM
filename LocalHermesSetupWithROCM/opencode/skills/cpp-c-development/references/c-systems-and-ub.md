# C11/C17 Systems Programming & Undefined Behavior Reference

## 1. Memory Layout, Alignment, and Struct Padding

Every object type has size `sizeof(T)` and alignment `_Alignof(T)` (from `<stdalign.h>`, `alignof(T)`). The compiler inserts padding between members and at the struct tail so every element in a `struct T arr[N]` meets `_Alignof(struct T)`.

- **Order fields largest-alignment to smallest** (`uint64_t`/pointers -> `uint32_t` -> `uint16_t` -> `uint8_t`) to minimize struct size and cache-line waste.
- **Never `memcmp` structs with padding:** padding bytes have unspecified values; equal logical fields can produce unequal `memcmp` results. Compare fields explicitly (or `memset` the whole struct to `0` before populating—though padding bytes are still unspecified after field writes in strict C11).
- **Never cast unaligned byte buffers to `uint32_t*`/`uint64_t*`:** misaligned dereference is UB (caught by `-fsanitize=alignment`, faults on strict-alignment targets). Use `memcpy`.

```c
#include <stdalign.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>

// Bad: 24 bytes on LP64 (7 bytes pad after tag + 4 bytes tail pad)
struct BadHeader { uint8_t tag; uint64_t seq; uint32_t len; };

// Good: 16 bytes on LP64 (3 bytes pad, fits 4 per 64B cache line)
struct GoodHeader { uint64_t seq; uint32_t len; uint8_t tag; };
_Static_assert(sizeof(struct GoodHeader) == 16, "unexpected padding");

// Flexible Array Member (FAM): allocate header + payload in one block
struct Packet {
    size_t len;
    uint8_t data[]; // must be last; sizeof(struct Packet) ignores data[]
};

struct Packet *packet_alloc(size_t len) {
    if (len > SIZE_MAX - sizeof(struct Packet)) return NULL;
    struct Packet *p = malloc(sizeof(*p) + len);
    if (p) p->len = len;
    return p;
}
```

## 2. Strict Aliasing & Type Punning

Under C11/C17 §6.5p7, an object with effective type `T1` may only be accessed through an lvalue of compatible type, signed/unsigned variant, aggregate containing `T1`, or a **character type** (`char`, `unsigned char`, `signed char`).

- **UB:** `float f = 1.0f; uint32_t bits = *(uint32_t *)&f;` — compiler may reorder or elide loads/stores assuming `float*` and `uint32_t*` never alias.
- **Note on `union` punning:** Permitted as a C11/C17 extension/footnote when representation fits, but **UB in C++**.
- **Portable zero-overhead fix (`memcpy`):** Compilers optimize fixed-size `memcpy` to a single register move (`movd`/`vmovd`).

```c
#include <assert.h>
#include <stdint.h>
#include <string.h>

static inline uint32_t float_to_bits(float f) {
    uint32_t bits;
    static_assert(sizeof(bits) == sizeof(f), "size mismatch");
    memcpy(&bits, &f, sizeof(bits));
    return bits;
}

static inline uint32_t read_le32(const uint8_t *buf) {
    return (uint32_t)buf[0] | ((uint32_t)buf[1] << 8) |
           ((uint32_t)buf[2] << 16) | ((uint32_t)buf[3] << 24);
}
```

- **`restrict` contract:** Declaring `void copy(size_t n, uint8_t *restrict dst, const uint8_t *restrict src)` promises `dst[0..n)` and `src[0..n)` do not overlap. Overlapping them is UB (use `memmove` when overlap is possible).

## 3. Pointer Provenance & Bounds Rules

Pointers carry **provenance** (the originating allocation object), not merely a numeric integer address.

- **One-past-the-end is the strict limit:** Given `int a[N]`, `a + N` is valid to form and compare (`p < a + N`), **UB to dereference**. Forming `a - 1` or `a + N + 1` is **immediate UB** even if never dereferenced.
- **Relational comparisons (`<`, `<=`, `>`, `>=`):** Defined **only** for pointers into the same array/allocation (or one-past-the-end). Comparing pointers from separate `malloc` calls is UB; only `==` and `!=` are valid across distinct objects.
- **Do not launder pointers through `uintptr_t` across objects:** Subtracting `(uintptr_t)p2 - (uintptr_t)p1` and adding the delta back to `p1` does **not** produce a valid pointer to `p2`'s object; optimizers may assume `p1 + delta` still aliases `p1`'s object only.

## 4. Signed Integer Overflow & Promotion Traps

Signed integer overflow (`INT_MAX + 1`, `INT_MIN / -1`, `INT_MIN % -1`, shifting a negative left operand, or shifting `>=` bit-width) is **UB**. Compilers use signed non-overflow invariants to eliminate security checks like `if (x + len < x)`!

- **Unsigned arithmetic wraps modulo $2^W$ (well-defined).**
- **Integer promotion trap:** Types narrower than `int` (`uint8_t`, `uint16_t`) promote to **signed `int`** before arithmetic. On 32-bit `int`, `uint16_t a = 60000, b = 60000; uint32_t c = a * b;` overflows signed `int` -> **UB**! Always cast: `(uint32_t)a * (uint32_t)b`.

```c
#include <limits.h>
#include <stdbool.h>
#include <stdint.h>

// Portable pre-check before signed addition
static inline bool checked_add_int(int a, int b, int *out) {
    if ((b > 0 && a > INT_MAX - b) || (b < 0 && a < INT_MIN - b)) return false;
    *out = a + b;
    return true;
}

// Clang/GCC builtin (or C23 <stdckdint.h> ckd_add/ckd_mul)
static inline bool checked_mul_size(size_t a, size_t b, size_t *out) {
#if defined(__GNUC__) || defined(__clang__)
    return !__builtin_mul_overflow(a, b, out);
#else
    if (a != 0 && b > SIZE_MAX / a) return false;
    *out = a * b;
    return true;
#endif
}
```

## 5. Arena (Bump) Allocator

Arenas eliminate per-object `free`, fragmentation, and leak graphs for phase-scoped or request-scoped lifetimes.

```c
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#if defined(__has_feature)
#  if __has_feature(address_sanitizer)
#    include <sanitizer/asan_interface.h>
#  endif
#endif

typedef struct {
    uint8_t *base;
    size_t cap;
    size_t offset;
} Arena;

static inline bool arena_init(Arena *a, size_t cap) {
    a->base = malloc(cap);
    a->cap = a->base ? cap : 0;
    a->offset = 0;
#ifdef ASAN_POISON_MEMORY_REGION
    if (a->base) ASAN_POISON_MEMORY_REGION(a->base, a->cap);
#endif
    return a->base != NULL;
}

static inline void *arena_alloc(Arena *a, size_t size, size_t align) {
    if (align == 0 || (align & (align - 1)) != 0) return NULL;
    if (size == 0) size = 1;
    uintptr_t cur = (uintptr_t)a->base + a->offset;
    size_t misalign = (size_t)(cur & (align - 1u));
    size_t pad = misalign ? (align - misalign) : 0;
    if (pad > a->cap - a->offset || size > a->cap - a->offset - pad) return NULL;

    uint8_t *ptr = a->base + a->offset + pad; // preserves a->base provenance
    a->offset += pad + size;
#ifdef ASAN_UNPOISON_MEMORY_REGION
    ASAN_UNPOISON_MEMORY_REGION(ptr, size);
#endif
    return ptr;
}

static inline void arena_reset(Arena *a) {
    a->offset = 0;
#ifdef ASAN_POISON_MEMORY_REGION
    if (a->base) ASAN_POISON_MEMORY_REGION(a->base, a->cap);
#endif
}

static inline void arena_destroy(Arena *a) {
#ifdef ASAN_UNPOISON_MEMORY_REGION
    if (a->base) ASAN_UNPOISON_MEMORY_REGION(a->base, a->cap);
#endif
    free(a->base);
    *a = (Arena){0};
}
```

Manual ASan poisoning lets AddressSanitizer catch use-after-`arena_reset` and intra-arena buffer overruns that `malloc`-level ASan would otherwise miss.

## 6. `goto cleanup` Multi-Resource Error Pattern

Initialize all resource handles to safe sentinel values at declaration, branch to a single `cleanup:` tail on error, and release in reverse acquisition order.

```c
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdlib.h>
#include <unistd.h>

int process_file(const char *path, size_t max_bytes) {
    int rc = -1;
    int saved_errno = 0;
    int fd = -1;
    uint8_t *buf = NULL;

    fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) goto cleanup;

    buf = malloc(max_bytes ? max_bytes : 1);
    if (!buf) goto cleanup;

    // realloc trap: never assign `buf = realloc(buf, new_sz)` directly!
    size_t grown = max_bytes * 2;
    if (grown < max_bytes) { errno = EOVERFLOW; goto cleanup; }
    uint8_t *tmp = realloc(buf, grown ? grown : 1);
    if (!tmp) goto cleanup; // original buf still freed in cleanup
    buf = tmp;

    rc = 0;

cleanup:
    saved_errno = errno; // preserve failure errno across free/close
    free(buf);           // free(NULL) is a guaranteed no-op
    if (fd >= 0) close(fd);
    if (rc != 0) errno = saved_errno;
    return rc;
}
```

## 7. Safe `(ptr, len)` String & Buffer Handling

- **Banned functions:** `gets`, `strcpy`, `strcat`, `sprintf`, `vsprintf`, `scanf("%s")`. Also avoid `strncpy` (omits NUL terminator on truncation and zero-fills the entire remaining buffer).
- **Slice convention:** Pass non-owning input strings/buffers as `(const char *ptr, size_t len)` and output buffers as `(char *dst, size_t dst_cap)`.
- **`snprintf` traps:**
  - `snprintf` returns the number of characters that **would have been written** (excluding NUL), NOT bytes written.
  - Truncation occurred if `n < 0 || (size_t)n >= cap`.
  - Never accumulate `pos += snprintf(buf + pos, cap - pos, ...)` without checking truncation first—once `pos >= cap`, `cap - pos` wraps to near `SIZE_MAX`.

```c
#include <stdarg.h>
#include <stdbool.h>
#include <stdio.h>

typedef struct {
    char *data;
    size_t cap;
    size_t len;
    bool truncated;
} StrBuf;

void strbuf_appendf(StrBuf *sb, const char *fmt, ...) {
    if (sb->truncated || sb->len >= sb->cap) { sb->truncated = true; return; }
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(sb->data + sb->len, sb->cap - sb->len, fmt, ap);
    va_end(ap);
    if (n < 0 || (size_t)n >= sb->cap - sb->len) {
        sb->len = sb->cap ? sb->cap - 1 : 0;
        if (sb->cap) sb->data[sb->len] = '\0';
        sb->truncated = true;
        return;
    }
    sb->len += (size_t)n;
}
```

## 8. POSIX `EINTR` & Partial Read/Write Loops

`read()`, `write()`, `recv()`, and `send()` may transfer fewer bytes than requested on sockets, pipes, or large files, or return `-1` with `errno == EINTR` when interrupted by a signal before transferring any byte.

```c
#include <errno.h>
#include <limits.h>
#include <stdint.h>
#include <unistd.h>

// Returns bytes read (< len only on EOF), or -1 on error.
ssize_t read_exact(int fd, void *buf, size_t len) {
    if (len > (size_t)SSIZE_MAX) { errno = EINVAL; return -1; }
    uint8_t *p = buf;
    size_t off = 0;
    while (off < len) {
        ssize_t n = read(fd, p + off, len - off);
        if (n > 0) { off += (size_t)n; continue; }
        if (n == 0) break; // EOF
        if (errno == EINTR) continue;
        return -1; // includes EAGAIN/EWOULDBLOCK on non-blocking fds
    }
    return (ssize_t)off;
}

// Returns 0 when all len bytes are written, or -1 on error.
int write_all(int fd, const void *buf, size_t len) {
    const uint8_t *p = buf;
    size_t off = 0;
    while (off < len) {
        ssize_t n = write(fd, p + off, len - off);
        if (n > 0) { off += (size_t)n; continue; }
        if (n == 0) { errno = EIO; return -1; } // prevent spin
        if (errno == EINTR) continue;
        return -1;
    }
    return 0;
}
```

- **Socket `SIGPIPE`:** Writing to a peer-closed socket/pipe raises `SIGPIPE` (killing the process by default). Use `send(..., MSG_NOSIGNAL)` on Linux or ignore `SIGPIPE` (`signal(SIGPIPE, SIG_IGN)`) so `write`/`send` returns `-1` with `errno == EPIPE`.
- **`SA_RESTART` limits:** Even with `SA_RESTART`, `poll`/`epoll_wait`/`select` and socket calls with `SO_RCVTIMEO`/`SO_SNDTIMEO` still fail with `EINTR`. Always loop on `EINTR` explicitly.

## 9. ABI & Header Hygiene

- **Include guards & minimal headers:** Guard every `.h` with `#ifndef PROJ_MODULE_H` / `#define PROJ_MODULE_H`. Use forward declarations (`struct MyCtx;`) when headers only reference pointers.
- **C++ interop:** Wrap declarations in `extern "C"` so C++ callers do not mangle symbol names, and **never** allow C++ exceptions to unwind across an `extern "C"` boundary (catch at the boundary and return an integer error code).
- **Opaque structs (C PIMPL):** Hide struct fields in `.c` so callers cannot stack-allocate or depend on `sizeof` or field offsets—preserving binary compatibility across library upgrades.
- **Symbol visibility & fixed types:** Compile shared libraries with `-fvisibility=hidden` and annotate exported functions explicitly; prefer `<stdint.h>` (`uint32_t`, `int64_t`) and `size_t` over `long` (which varies between LP64 Linux and LLP64 Windows) in public ABIs.

```c
#ifndef MYLIB_CLIENT_H
#define MYLIB_CLIENT_H

#include <stddef.h>
#include <stdint.h>

#if defined(_WIN32)
#  define MYLIB_API __declspec(dllexport)
#elif defined(__GNUC__) || defined(__clang__)
#  define MYLIB_API __attribute__((visibility("default")))
#else
#  define MYLIB_API
#endif

#ifdef __cplusplus
extern "C" {
#endif

typedef struct mylib_client mylib_client; // opaque handle

MYLIB_API mylib_client *mylib_client_create(uint32_t timeout_ms);
MYLIB_API int mylib_client_send(mylib_client *c, const uint8_t *buf, size_t len);
MYLIB_API void mylib_client_destroy(mylib_client *c); // must tolerate NULL

#ifdef __cplusplus
}
#endif
#endif
```

## 10. Verification & Debugging Checklist

- **Compiler baseline:** `-std=c17 -Wall -Wextra -Wpedantic -Wshadow -Wconversion -Wstrict-prototypes -Werror=implicit-function-declaration`.
- **Sanitizer run (dev/CI):** `-O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined` with `UBSAN_OPTIONS=print_stacktrace=1:halt_on_error=1`.
- **Layout & static inspection:** `pahole build/mylib.o` (inspect struct holes/cache-line splits), `clang-tidy`, `cppcheck`, or `valgrind --leak-check=full --track-origins=yes` (on non-ASan builds).
