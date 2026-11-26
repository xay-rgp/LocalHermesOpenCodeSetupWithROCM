# JavaScript & TypeScript Mastery Reference

## 1. JS Event Loop: Microtasks, Macrotasks, and Starvation

Single-threaded JS executes one synchronous call stack frame to completion, then drains queues in strict priority:

1. **Current synchronous call stack** runs until empty.
2. **Microtask queue drains completely** (including any new microtasks enqueued during draining):
   - Node.js `process.nextTick` queue drains **before** Promise microtasks (can starve Promises if abused).
   - `Promise.then/catch/finally`, `await` continuations, `queueMicrotask`, `MutationObserver`.
3. **Browser render phase** (style/layout/paint/`requestAnimationFrame`, when frame due) OR **Node poll/check phases**.
4. **One macrotask** (`setTimeout`, `setInterval`, I/O callback, Node `setImmediate`, UI click) runs, then loop returns to step 2.

```js
console.log("1: sync");
setTimeout(() => console.log("4: macrotask (timer)"), 0);
Promise.resolve().then(() => {
  console.log("2: microtask");
  queueMicrotask(() => console.log("3: nested microtask (before timer!)"));
});
```

- **Microtask starvation:** Recursively scheduling `queueMicrotask(loop)` or `Promise.resolve().then(loop)` blocks timers, I/O, and rendering forever. Break long CPU loops by yielding to a macrotask (`await new Promise(r => setTimeout(r, 0))` or `await scheduler.yield()` in modern browsers).

## 2. Closures & Memory Leaks

A closure captures a shared lexical environment record (`Scope`). In V8, **if two inner closures exist in the same parent scope, they share one context object**—any large variable referenced by *either* closure stays alive while *either* closure survives.

### Top Leak Patterns & Fixes
1. **Unremoved event listeners / detached DOM nodes:** Listeners attached to `window`, `document`, `EventEmitter`, or singletons hold their closure and target subtree alive forever. Pass `{ signal: controller.signal }` to `addEventListener` or pair `on`/`off`.
2. **Uncancelled `setInterval` / orphan timers:** Always `clearInterval` on teardown or bind via `AbortSignal`.
3. **Unbounded module caches (`Map` / `{}`):** Use `WeakMap`/`WeakSet` when keying by object lifetime, or an explicit bounded LRU cache. Use `FinalizationRegistry` only for telemetry/last-resort native cleanup (GC timing is non-deterministic).

- **Debugging:** Launch Node with `node --inspect` -> Chrome DevTools Memory tab -> take Heap Snapshot before/after workload + GC -> compare **Objects allocated between Snapshot 1 and 2** (search `"Detached"` in browser DOM leaks).

## 3. Prototype Chain, `Object.create(null)`, `Map`, and Prototype Pollution

Property access `obj.k` walks `obj -> Object.getPrototypeOf(obj) -> ... -> Object.prototype -> null`.

- **Prototype pollution:** Deep-merging untrusted JSON containing `"__proto__"`, `"constructor"`, or `"prototype"` keys into `{}` mutates `Object.prototype` across the entire process:
  ```js
  // Vulnerable merge:
  target[key] = source[key]; // if key === "__proto__", mutates Object.prototype!
  ```
- **Defenses:**
  - **Prefer `Map`** (`new Map()`) for arbitrary/user-supplied keys: immune to `__proto__`, `toString`, `constructor` collisions, O(1) lookup, clean `.size`.
  - **Use `Object.create(null)`** when a plain dictionary is needed (zero prototype; inspect keys safely with `Object.hasOwn(obj, key)` ES2022, never `obj.hasOwnProperty(key)` because `Object.create(null)` lacks it).
  - **Validate & guard merges:** Reject `key === "__proto__" || key === "constructor" || key === "prototype"`, and validate external JSON at boundaries (e.g. Zod).

## 4. Strict TypeScript Configuration

Minimum production `tsconfig.json` compiler options:

```json
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "noImplicitOverride": true,
    "noFallthroughCasesInSwitch": true,
    "verbatimModuleSyntax": true,
    "useUnknownInCatchVariables": true,
    "module": "nodenext",
    "moduleResolution": "nodenext",
    "skipLibCheck": true
  }
}
```

- **`noUncheckedIndexedAccess`:** Makes `arr[i]` and `dict[key]` return `T | undefined`, eliminating silent runtime `Cannot read properties of undefined` bugs.
- **`exactOptionalPropertyTypes`:** Separates `{ timeout?: number }` (omitted or `number`) from `{ timeout?: number | undefined }` (explicit `undefined` allowed). Catches accidental `{ timeout: undefined }` overwrites during object spreading.
- **`verbatimModuleSyntax`:** Forces explicit `import type { Foo }` so type-only imports are cleanly erased in ESM output.

## 5. Discriminated Unions & Exhaustive `never` Check

Model state machines and errors with a literal discriminant tag and enforce exhaustiveness at compile time:

```ts
type Result<T, E> =
  | { ok: true; value: T }
  | { ok: false; error: E };

function assertNever(x: never): never {
  throw new Error(`Unhandled variant: ${JSON.stringify(x)}`);
}

type JobState =
  | { kind: "queued"; runAt: number }
  | { kind: "running"; workerId: string }
  | { kind: "failed"; reason: string };

function formatJob(s: JobState): string {
  switch (s.kind) {
    case "queued":  return `queued@${s.runAt}`;
    case "running": return `worker:${s.workerId}`;
    case "failed":  return `err:${s.reason}`;
    default:        return assertNever(s); // compile error if a new kind is added!
  }
}
```

## 6. Conditional, Mapped, and Template Literal Types

```ts
// Conditional + infer (distributes over naked union T)
type UnwrapPromise<T> = T extends Promise<infer U> ? UnwrapPromise<U> : T;
// Wrap in tuple `[T] extends [U]` to DISABLE distribution over unions
type IsUnionMemberArray<T> = [T] extends [string | number] ? true : false;

// Mapped type with key remapping (`as`) and modifier control
type Getters<T> = {
  readonly [K in keyof T as `get${Capitalize<string & K>}`]: () => T[K];
};

// Template literal types for compile-time string invariants
type HttpMethod = "GET" | "POST";
type RouteKey = `${HttpMethod} /${string}`;
const route: RouteKey = "GET /users"; // "PUT /users" is a compile error
```

## 7. `satisfies`, `unknown` vs `any`, and Narrowing

- **`satisfies` operator:** Checks conformance against a target type **without widening** the inferred literal/tuple types and without unsound casting (`as`):
  ```ts
  type Palette = Record<string, string | [number, number, number]>;
  const colors = {
    red: [255, 0, 0],
    green: "#00ff00",
  } satisfies Palette;

  colors.green.toUpperCase(); // OK: still inferred as string, not `string | [...]`
  colors.red[0];              // OK: tuple length 3 preserved
  ```
- **`unknown` vs `any`:**
  - `any` turns off type checking and infects downstream types.
  - `unknown` is the **type-safe top type**: anything assigns to `unknown`, nothing can be used until narrowed via `typeof`, `Array.isArray`, `in`, or a type predicate:
  ```ts
  function isApiError(x: unknown): x is { code: number; message: string } {
    return (
      typeof x === "object" && x !== null &&
      "code" in x && typeof x.code === "number" &&
      "message" in x && typeof x.message === "string"
    );
  }
  ```

## 8. `AbortController` / `AbortSignal` Cancellation & `Promise.allSettled`

Propagate `signal` through `fetch`, timers (`node:timers/promises`), streams, and `addEventListener`.

```ts
async function fetchWithDeadline(url: string, callerSignal?: AbortSignal): Promise<Response> {
  const timeout = AbortSignal.timeout(5_000);
  // Node 20+ / modern browsers: combine caller cancel + timeout with zero listener leaks
  const signal = callerSignal ? AbortSignal.any([callerSignal, timeout]) : timeout;

  const res = await fetch(url, { signal });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res;
}

// Promise.all rejects fast while siblings keep running silently.
// Promise.allSettled waits for every task so errors and cleanup are observed.
async function runBatch(urls: string[], signal: AbortSignal) {
  const settled = await Promise.allSettled(urls.map((u) => fetchWithDeadline(u, signal)));
  const ok = [];
  const errors = [];
  for (const item of settled) {
    if (item.status === "fulfilled") ok.push(item.value);
    else errors.push(item.reason);
  }
  return { ok, errors };
}
```

- **Caution:** `Promise.allSettled` launches every promise immediately; bound large batches with a concurrency limit (`p-limit` or a worker queue) so 10k URLs do not open 10k sockets.

## 9. ESM vs CJS Pitfalls

- **ESM (`"type": "module"` / `.mjs`):** Async static graph, always strict mode, **no `__dirname` / `__filename` / `require`**. Use `import.meta.dirname` (Node 20.11+) or `path.dirname(fileURLToPath(import.meta.url))`.
- **Node ESM explicit extensions:** Under `"moduleResolution": "nodenext"`, relative imports in `.ts` files must write the **emitted `.js` extension** (`import { db } from "./db.js";`).
- **Dual-package hazard:** Importing the same library via CJS `require` and ESM `import` can load two copies of the module, breaking `instanceof` checks and module-level singletons.
- **Default export interop:** CJS `module.exports = fn` imported into ESM may arrive as `mod.default` depending on bundler/Node flags (`esModuleInterop`). Prefer named exports everywhere.

## 10. Verification

- Type check: `npx tsc --noEmit`
- Lint type-aware rules (`no-floating-promises`, `no-unsafe-assignment`, `no-explicit-any`): `npx eslint .`
- Runtime & leak check: `node --test` / `vitest run` and `node --trace-warnings`
