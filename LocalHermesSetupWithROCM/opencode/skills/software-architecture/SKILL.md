---
name: software-architecture
description: "Design clean, modular, secure APIs, DBs, and systems."
version: 1.0.0
author: Xay, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [architecture, solid, design-patterns, api, database, security, performance]
    related_skills: [python-development, rust-development, testing-qa, debugging-mastery]
---

# Software Architecture

Pragmatic software engineering for clean architecture, SOLID principles, design patterns, modular design, APIs, databases, security, dependency hygiene, and performance optimization.

## When to Use

- Designing a new service, CLI, library, database schema, or API contract
- Refactoring tightly coupled code, untangling circular dependencies, or breaking up god classes
- Reviewing system security, caching, scalability, or maintainability trade-offs
- Don't use for: single-function syntax questions or language-specific compiler diagnostics

## Core Architectural Principles

1. **Enforce the Dependency Rule (Clean / Hexagonal Architecture).** Domain logic must depend ONLY on domain types and narrow port interfaces — never on HTTP frameworks, ORMs, CLI parsers, or vendor SDKs. Infrastructure adapters depend inward on the domain.
2. **Apply SOLID pragmatically, never dogmatically.**
   - **S (Single Responsibility):** One coherent reason to change per module/class (not one method per class).
   - **O (Open/Closed):** Extend behavior via composition/protocols/plugins instead of editing central `if/elif` switches across the codebase.
   - **L (Liskov Substitution):** Subtypes must honor caller preconditions/postconditions; never throw `NotImplementedError` from an inherited method.
   - **I (Interface Segregation):** Narrow, caller-owned interfaces (`Reader`, `Clock`, `UserStore`) beat 20-method god interfaces.
   - **D (Dependency Inversion):** Inject side-effecting dependencies (`Clock`, `HttpClient`, `Repo`) at the composition root (`main`) so business logic is trivially testable.
3. **Prefer composition and plain data over deep inheritance.** Inheritance couples subclasses to parent internals; composition with small interfaces stays flexible.
4. **Design for zero-downtime evolution.** Schema changes use expand-and-contract migrations; APIs use additive changes, explicit versioning, and idempotency keys on mutations.
5. **Measure before optimizing.** Profile latency, memory, and query plans first. Algorithmic/architectural fixes (eliminating N+1 queries, adding the right index, batching I/O) beat micro-optimizations by orders of magnitude.

## Quick Reference

| Area | Production Standard | Anti-Pattern |
|---|---|---|
| Module boundaries | Feature/domain vertical slices + explicit public API | Shared mutable globals, circular imports |
| API mutations | `Idempotency-Key` header + deterministic 4xx/5xx error schema | Non-idempotent retries creating duplicate charges/rows |
| Pagination | Keyset/cursor pagination (`WHERE id > $cursor`) | `OFFSET 100000` (O(N) scan + drift on inserts) |
| DB migrations | Expand → backfill → switch reads/writes → contract | Destructive `DROP COLUMN` / table-locking `ALTER` in one deploy |
| Dependencies | Lockfile committed, minimal transitive tree, pinned digests | Unpinned `*`/`latest`, vendoring unmaintained forks |
| Security | Parameterized SQL, least privilege, constant-time token compare | String-interpolated SQL, secrets in logs/repo, client-only authz |

## Deep References

Load on demand with `skill_view("software-architecture", file_path="...")`:
- `references/clean-architecture-patterns.md` — Hexagonal boundaries, SOLID examples, GoF & distributed patterns (Strategy, State, Adapter, Outbox, Circuit Breaker, CQRS), and when NOT to add abstraction.
- `references/apis-databases-security.md` — REST/gRPC/GraphQL contracts, DB indexing/isolation/migrations, caching & stampede control, OWASP security checklist, dependency management, observability.

## Architecture Design Procedure

1. **Inspect existing code and constraints.** Read existing entry points (`read_file`, `search_files`), data models, and operational limits (latency, throughput, consistency, deployment target). Completion criterion: boundaries, invariants, and failure modes are explicitly listed.
2. **Define domain model and seams.** Specify core entities, value objects, invariants, and external ports (DB, network, clock, filesystem). Completion criterion: domain module imports zero I/O frameworks.
3. **Design contracts and failure behavior.** Specify API schemas, HTTP/gRPC status codes, timeouts, retry/backoff rules, and idempotency semantics. Completion criterion: every external call has a timeout, bounded retry policy, and typed error mapping.
4. **Validate security and operational readiness.** Check authn/authz enforcement at every endpoint, input validation, parameterized queries, structured logging (no secrets), and rollback safety. Completion criterion: threat surface and migration rollback steps are documented and verified.

## Common Pitfalls

- **Premature abstraction (Rule of Three violation):** Extracting a generic framework for a single use case creates indirection without reuse. Wait until 2–3 concrete implementations reveal the true shared seam.
- **Leaky ORM abstractions:** Passing lazy-loaded ORM entities into templates or serializers triggers silent N+1 queries and couples domain logic to DB sessions. Map to explicit DTOs/domain dataclasses at the repository boundary.
- **Distributed monolith:** Splitting into microservices that share a database or require synchronous lockstep deploys adds network failure modes without decoupling. Start with a well-structured modular monolith.
- **Unbounded queues and missing backpressure:** Accepting work faster than downstream can drain it guarantees OOM crashes under load. Bound queues, rate-limit ingress, and shed load with HTTP 429/503.
- **Missing authorization on object IDs (IDOR/BOLA):** Checking "user is logged in" without verifying `resource.owner_id == current_user.id` is the #1 API vulnerability.
- **Check-then-insert idempotency race (TOCTOU):** Doing `SELECT` then `INSERT` without a `UNIQUE` index allows concurrent retries to insert duplicates. Enforce a `UNIQUE` index on `(tenant_or_user, idempotency_key)` and use `INSERT ... ON CONFLICT DO NOTHING` / `INSERT OR IGNORE` followed by `SELECT`.
- **Over-caching stale/mutable state:** Adding Redis before fixing slow SQL queries introduces cache-invalidation bugs and thundering herds.

## Verification

- Verify acyclic module dependencies (no circular imports; domain layer has zero infrastructure imports).
- Run schema migrations forward AND verify backward compatibility with the previous code version.
- Execute integration tests covering authz denials, idempotent retries, invalid payloads, and downstream timeouts.
