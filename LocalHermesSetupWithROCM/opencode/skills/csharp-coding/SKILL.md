---
name: csharp-coding
description: "Write modern C#/.NET with nullability, LINQ, and async."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [csharp, dotnet, linq, async, nullable, records, xunit]
    related_skills: [software-architecture, testing-qa, debugging-mastery]
---

# C# and .NET Coding

Idiomatic C# 12 / .NET 8 engineering covering nullable reference types, immutable records, interfaces, LINQ, structured `async`/`await` with `CancellationToken`, and xUnit testing.

## When to Use

- Writing, refactoring, or debugging C# libraries, services, data models, LINQ queries, or `async`/`await` workflows
- Fixing nullability warnings, async deadlocks, deferred LINQ re-enumeration, or exception-handling bugs
- Authoring xUnit (`[Fact]`, `[Theory]`) unit tests for C# modules
- Don't use for: non-C# projects

## Core Discipline

1. **Always enable nullable reference types and use file-scoped namespaces:**
   ```csharp
   #nullable enable
   namespace MyApp.Domain;
   ```
   Use `[NotNullWhen(true)]` on `Try*` `out` parameters so callers get flow-analyzed non-nullability.
2. **Validate inputs with modern guard clauses:**
   - `ArgumentNullException.ThrowIfNull(arg);`
   - `ArgumentException.ThrowIfNullOrWhiteSpace(text);`
   - `ArgumentOutOfRangeException.ThrowIfNegativeOrZero(value);` (or explicit range checks).
3. **Prefer immutable `sealed record` / `readonly record struct` for data:**
   - Update records immutably via `current with { Status = nextStatus, ... }`.
   - Use `IReadOnlyList<T>` / `IReadOnlyDictionary<K, V>` for return types; never expose mutable `List<T>` fields directly.
   - Use generic collections (`Dictionary<K, V>`, `List<T>`); never legacy `ArrayList` or `Hashtable`.
4. **Use LINQ safely without multiple enumeration:**
   - Materialize query results (`.ToList()` / `.ToArray()`) before returning `IReadOnlyList<T>` or iterating multiple times.
   - Express multi-key sorting cleanly with `.OrderByDescending(...).ThenBy(...)`.
5. **Write deadlock-free `async`/`await`:**
   - Return `Task` / `Task<T>` / `ValueTask<T>` (never `async void` outside event handlers).
   - Accept `CancellationToken cancellationToken = default` on async APIs, pass it downstream, and call `cancellationToken.ThrowIfCancellationRequested()`.
   - Never block on async code with `.Result`, `.Wait()`, or `.GetAwaiter().GetResult()`, and never call `Thread.Sleep` inside async methods (use `await Task.Delay(..., cancellationToken)`).
   - Dispose resources via `using` / `await using`.
6. **Preserve exception stacks:**
   - Rethrow caught exceptions with bare `throw;`, NEVER `throw ex;` (which destroys the original stack trace). Never write empty `catch { }` blocks.
7. **Always write files to disk and verify syntax:**
   - When asked to create a `.cs` file, always invoke `write_file` (even if `dotnet` is not installed locally) and read the file back to confirm valid C# identifiers (no hyphenated enum names like `In-Progress`, no stray tokens, balanced braces).

## Common Pitfalls

- **Printing C# code in chat instead of calling `write_file`:** When `dotnet` isn't installed, still write the `.cs` file to disk with `write_file` and verify it via `read_file`.
- **Invalid identifiers & stray tokens:** C# enum/type/member names cannot contain hyphens (`InProgress`, not `In-Progress`). Never work around a mid-generation typo (like `DateTimeable?`) by creating a duplicate record/class (`OrderRecord`) or changing required interface signatures — finish the write, then use `patch` to fix the single typo in place! Before finishing, scan the file for stray bare words on their own line (e.g., `un`, `undetermine`) or corrupted identifiers (e.g., `RolloutintStage`), and verify record `with` updates are actually saved back into the backing dictionary (`_store[key] = updated;`).
- **Dispose `SemaphoreSlim` & place `WaitAsync` BEFORE `try`/`finally`:** Both `SemaphoreSlim` and `CancellationTokenSource` implement `IDisposable` — always write `using var semaphore = new SemaphoreSlim(...)` and `using var cts = new CancellationTokenSource()`. Always call `await semaphore.WaitAsync(cancellationToken);` **outside** `try { ... } finally { semaphore.Release(); }` so a canceled wait never over-releases the semaphore (`SemaphoreFullException`).
- **xUnit cancellation assertions (CRITICAL):** `Task.Delay` / `WaitAsync` throw `TaskCanceledException` (a subclass of `OperationCanceledException`). In xUnit, `Assert.ThrowsAsync<OperationCanceledException>` FAILS on subclasses — ALWAYS write `Assert.ThrowsAnyAsync<OperationCanceledException>`!
- **Bounded `Channel<T>` completion & disposal:** Call `_channel.Writer.TryComplete()` before `await foreach` consumers finish (otherwise `ReadAllAsync` waits forever), and in `DisposeAsync()` return `ValueTask.CompletedTask` after `TryComplete()` instead of awaiting `_channel.Reader.Completion` (which blocks if unread items remain).
- **Sync-over-async deadlocks:** Calling `.Result` or `.Wait()` on a `Task` starves thread-pool threads and deadlocks synchronization contexts.
- **Swallowing stack traces:** `catch (Exception ex) { Log(ex); throw ex; }` wipes the original stack frame — always use `throw;`.
- **Forgotten `#nullable enable`:** Without `#nullable enable` (or `<Nullable>enable</Nullable>` in `.csproj`), nullable annotations emit CS8632 warnings.

## Verification

- If `dotnet` is installed, run `dotnet build --warnaserror` and `dotnet test`.
- Otherwise, read back every written `.cs` file AND run a quick `python3` check via `terminal` verifying balanced `{}`/`()`/`[]`, `#nullable enable`, zero stray bare words on their own line (`^\s*[a-zA-Z_]\w*\s*$`), zero `// Wait`/`// Fix` comments, and complete `[Fact]`/`[Theory]` test coverage.

## Course 3 Senior Pitfalls (Verified)
- **Zero-Allocation Span Scanning:** Never call `key.ToCharArray()` when passing a string to `ReadOnlySpan<char>.IndexOf(...)` — pass `key.AsSpan()` or a `ReadOnlySpan<char>` literal directly to avoid heap allocations.
- **No Hallucinated APIs or Draft Comments:** Always use `ArgumentNullException.ThrowIfNull(arg)` (never invented names like `Nullify`), keep exact identifier casing/spelling, and never leave internal thinking/draft comments (`// Wait, ...`) inside `.cs` files.
- **Write Files Directly:** Always call `write_file` on Turn 1 rather than printing code blocks to chat.
- **Nullable Enum Switch Expressions & xUnit Type Narrowing:** When a `switch` expression returns a value-type enum or `null`, explicitly type the target as `MetricKind? kind = span switch { "c" => MetricKind.Counter, ..., _ => null };` (or cast the first arm `(MetricKind?)`) and pass `kind.Value` after `if (kind is null)`. In xUnit tests on discriminated unions, always capture `var ok = Assert.IsType<Result<T>.Ok>(result);` before accessing `ok.Value`.
- **`PeriodicTimer` Argument Order & Single-Waiter Rule:** The .NET 8 constructor is `new PeriodicTimer(TimeSpan period, TimeProvider timeProvider)` (interval FIRST, TimeProvider SECOND). Never create a new `WaitForNextTickAsync` task while a previous one is still pending; reuse the pending timer task across `Task.WhenAny` iterations. Always dispose `_cts` in `DisposeAsync()`, and match delegate arity in test lambdas (e.g. `(items, ct) => ...`).
