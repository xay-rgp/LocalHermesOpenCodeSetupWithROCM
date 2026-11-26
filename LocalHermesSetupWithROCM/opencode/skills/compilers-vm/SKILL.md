---
name: compilers-vm
description: Staff compiler, parser, regex NFA, bytecode VM, and garbage collector engineering patterns — zero-regex lexing with exact (line, col) spans, Pratt precedence parsing, lexical scope-stack type checking, Thompson NFA epsilon closure, C++20 stack VMs, and cyclic mark-and-sweep GC.
---

# Staff Compilers, Parsers & Virtual Machines

## Hand-Written Zero-Regex Lexers
- **Exact `(line, col)` Span Tracking:** Capture `start_line, start_col = line, col` before consuming a token. When reporting escape-sequence errors after advancing past `\`, report `col - 1` (the column of the backslash), and reset `col = 1; line += 1` on `\n`.
- **Two-Character Lookahead:** Always check two-character operators (`==`, `!=`, `<=`, `>=`) and `//` comments before single-character operators (`=`, `<`, `>`, `/`), and emit a final `EOF` token at the end of input.

## Lexical-Scope Static Type Checking
- **Scope Stack Discipline:** Represent environments as a `list[dict[str, str]]` stack (NEVER a single flat dict). Push a fresh dict on entering a `block` or `fn`, pop it in `finally` on exit, shadow `let` bindings in `scopes[-1]` only, and resolve `var`/`assign` from innermost to outermost scope (`reversed(scopes)`).
- **Strict Type Invariants:** Require `bool` (never `int`) for `if` conditions, verify function call arity & argument types, reject `return` outside functions, and enforce exact return-type matching.

## Tracing Mark-and-Sweep Garbage Collection
- **Iterative Worklist Traversal:** Always implement the Mark phase iteratively (`stack = list(self.roots); marked = set()`) rather than recursively so 5,000+ node object chains never hit recursion limits and cyclic object graphs terminate cleanly via `if curr_id not in marked:`.
- **Safe Sweep & Dangling-Ref Guards:** Sweep over `list(self.objects.keys())`, deleting any ID not in `marked`; validate every `ref_id` in `alloc()` / `set_refs()` / `add_root()` against live objects and raise `KeyError` on freed-object access.
