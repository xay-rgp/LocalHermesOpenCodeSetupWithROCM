---
name: lua-development
description: Senior Lua 5.4/5.5 engineering patterns — zero global leaks, metatable OOP without field/method shadowing, safe table mutation, coroutine scheduling, and sandboxed load() execution.
---

# Senior Lua Engineering

## Metatable OOP & Field Shadowing
- **Never Shadow Method Names with Instance Fields:** In Lua, raw table keys on `self` take precedence over `__index` metatable lookups. If a class defines `function Foo:capacity()`, NEVER store `self.capacity = cap` — prefix internal fields with an underscore (`self._capacity`, `self._count`, `self._head`, `self._storage`).
- **Strict Positive Finite Integer Validation:** Check `type(n) == "number" and n == n and n ~= math.huge and n >= 1 and math.floor(n) == n` (note: `math.huge > math.huge` is `false`, so test `n ~= math.huge`!).
- **Zero Global Leaks:** Always declare module tables, helpers, and loop variables `local`; verify zero accidental `_G` mutations.

## Instance Isolation & Safe Table Iteration (Lua)
- **Per-Instance Mutable State:** NEVER put mutable tables (`_listeners = {}`, `_history = {}`) on the prototype metatable — initialize fresh tables inside `Class.new()` so instances never corrupt each other.
- **Reverse Removal & Snapshot Dispatch:** Remove elements from sequence tables backward (`for i = #t, 1, -1`) so indices don't shift, and iterate over a shallow snapshot when callbacks may mutate listeners re-entrantly (e.g. `:once` or `:off` inside `:emit`).

## Coroutine Scheduling & Colon vs Dot Methods (Lua)
- **Dot vs Colon Calling Convention:** Define static module helpers with a dot (`function Scheduler.yield_ticks(n)`) and instance methods with a colon (`function Scheduler:sleep(ticks)`). Mismatching `.` and `:` shifts all arguments by one slot because `:` inserts an implicit `self`.
- **Cooperative Coroutine Isolation:** Resume tasks with `local ok, res = coroutine.resume(task.co)`; on failure (`not ok`), record `tostring(res)` in `self._errors[task.name]` and mark dead so sibling coroutines keep running unaffected.

## Sandboxed Evaluation (Lua 5.4/5.5)
- **Text-Only `load` & Hook Restoration:** Always compile untrusted code with `load(code, "sandbox", "t", env)` (mode `"t"` rejects binary bytecode). Before setting an instruction-limit hook, capture ALL THREE return values `local old_hook, old_mask, old_count = debug.gethook()`, and after `pcall(chunk)` restore via `if old_hook then debug.sethook(old_hook, old_mask, old_count) else debug.sethook() end`.
