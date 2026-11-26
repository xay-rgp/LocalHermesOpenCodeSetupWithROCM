# Rust Ownership, Lifetimes, and Trait System Reference

## 1. Ownership, Borrowing, and Non-Lexical Lifetimes (NLL)

- Every value has one owner; assignment/passing moves non-`Copy` values unless borrowed (`&T` shared/immutable, `&mut T` exclusive/mutable).
- **Aliasing XOR Mutability:** Any number of `&T` OR exactly one `&mut T` may be active simultaneously. This single invariant prevents data races, iterator invalidation, and use-after-free at compile time.
- **NLL:** A borrow ends at its **last use**, not at the end of the lexical block `{ ... }`.
- **Disjoint field borrows:** Borrowing `&mut s.a` and `&mut s.b` simultaneously works in direct expressions, but NOT across a method `&mut self` (methods lock the whole struct). Fix by splitting into free functions or helper sub-structs (`s.split_parts_mut()`).

## 2. Lifetimes, Elision, Variance, and HRTB

### Lifetime Elision Rules
1. Each elided input lifetime gets its own parameter: `fn f(x: &str, y: &str)` -> `fn f<'a, 'b>(x: &'a str, y: &'b str)`.
2. If there is exactly one input lifetime, it is assigned to all elided output lifetimes.
3. If one input is `&self` or `&mut self`, its lifetime is assigned to all elided output lifetimes.

### Common Lifetime Traps & Fixes
- **`&'a mut T` is invariant in `T`:** You cannot coerce `&'a mut &'static str` to `&'a mut &'short str` (otherwise writing a short-lived ref through it would leave a dangling pointer in the `'static` slot).
- **`&'a T` is covariant in both `'a` and `T`:** A `&'static str` can always be shortened to `&'a str`.
- **Avoid `&'a mut Struct<'a>`:** Tying a struct's own lifetime parameter to a mutable borrow of itself locks the struct exclusively for its entire remaining life — almost always an API bug.
- **Higher-Ranked Trait Bounds (HRTB):** When a closure must work for *any* lifetime chosen by the callee, write `F: for<'a> Fn(&'a str) -> &'a str` instead of tying `'a` to the outer function.

## 3. Interior Mutability & Smart Pointers

| Type | Thread-Safe? | Borrow Check | Use Case |
|---|---|---|---|
| `Box<T>` | If `T: Send/Sync` | Compile-time | Heap allocation, recursive types, `Box<dyn Trait>` |
| `Rc<T>` / `Arc<T>` | `Rc`: No / `Arc`: Yes | Compile-time (immutable) | Shared ownership; break cycles with `Weak<T>` |
| `Cell<T>` | No (`!Sync`) | Zero-cost copy/replace | Small `Copy` counters/flags in single-threaded code |
| `RefCell<T>` | No (`!Sync`) | Runtime (`borrow`/`borrow_mut` panic on conflict) | Rarely needed; prefer restructuring or indices |
| `Mutex<T>` / `RwLock<T>` | Yes (`Sync` if `T: Send`) | Runtime lock | Short critical sections across threads |
| `Cow<'a, str>` | If owned is | Compile-time | Borrow zero-copy in common case, allocate only on mutation |

### Graph / Cyclic Structures Without `Rc<RefCell<T>>`
Use an **arena / slab** (`Vec<Node>` + `struct NodeId(usize)` or `slotmap::SlotMap`). Benefits: cache locality, trivial `Copy` handles, zero reference cycles, effortless serialization, no runtime borrow panics.

## 4. Traits, Generics, Object Safety, and Typestate

### Static vs Dynamic Dispatch
- **Static (`fn run<T: Handler>(h: &T)` / `impl Handler`):** Monomorphized per concrete type — inlined, zero vtable overhead, larger binary size.
- **Dynamic (`&dyn Handler` / `Box<dyn Handler>`):** Single compiled body + vtable pointer — supports heterogeneous `Vec<Box<dyn Handler>>`, faster compile times.
- **Dyn-compatibility (object safety) rules:** A trait can be `dyn Trait` only if its methods (without `where Self: Sized`) have a receiver (`&self`, `&mut self`, `Box<Self>`), no generic type parameters on the method, and do not return bare `Self`.

### Typestate Pattern (Compile-Time State Machine)
```rust
use std::marker::PhantomData;

struct Unauthenticated;
struct Authenticated;

struct Session<State> {
    user: String,
    _state: PhantomData<State>,
}

impl Session<Unauthenticated> {
    pub fn new(user: String) -> Self {
        Self { user, _state: PhantomData }
    }
    pub fn authenticate(self, ok: bool) -> Result<Session<Authenticated>, &'static str> {
        if ok { Ok(Session { user: self.user, _state: PhantomData }) } else { Err("denied") }
    }
}

impl Session<Authenticated> {
    pub fn read_secret(&self) -> &str { &self.user }
}
```
Calling `read_secret()` on an unauthenticated session is a compile error, with zero runtime overhead (`PhantomData` is 0 bytes).

### Extension & Conversion Traits
- Implement `From<A> for B` (never `Into` directly — `Into` is auto-derived).
- Accept `impl AsRef<Path>` or `impl Into<String>` cleanly when ergonomics matter, but avoid over-genericizing internal helpers where concrete types keep error messages clear.
- Implement `Default`, `Debug`, `Clone`, `PartialEq` thoughtfully; derive `Copy` only on small stack types that will never own heap memory.
