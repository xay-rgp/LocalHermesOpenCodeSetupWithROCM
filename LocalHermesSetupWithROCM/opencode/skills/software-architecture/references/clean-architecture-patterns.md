# Clean Architecture, SOLID, and Design Patterns Reference

## 1. Clean / Hexagonal Architecture (Ports & Adapters)

### The Dependency Rule
Source code dependencies point **strictly inward**. Outer layers (`adapters`, frameworks, ORMs, CLI) depend on inner layers (`application`, `domain`); inner layers import **zero** I/O libraries, ORMs, HTTP frameworks, or vendor SDKs.

```
  Inbound Adapters          Application / Use Cases            Domain Core (Pure)
  (HTTP / CLI / Queue) ───▶ (Orchestration + Ports) ─────────▶ (Entities, Values, Rules)
                                    ▲
                                    │ implements
                            Outbound Adapters
                        (Postgres / Stripe / Clock)
```

### Canonical Directory Layout
```text
src/orders/
├── domain/                  # Pure logic: ZERO framework/I/O imports
│   ├── model.py             # Entities, Value Objects, State invariants
│   └── errors.py            # DomainError hierarchy (no HTTP status codes!)
├── ports/                   # Narrow interfaces owned by domain/application
│   ├── repositories.py      # OrderRepository(Protocol), UnitOfWork(Protocol)
│   └── gateways.py          # PaymentGateway(Protocol), Clock(Protocol)
├── application/             # Use-case orchestration (depends ONLY on domain + ports)
│   └── place_order.py       # Transactional workflow, maps ports -> domain calls
├── adapters/
│   ├── inbound/             # Translates transport -> use-case input DTOs
│   │   ├── http_routes.py   # FastAPI/Axum handlers, validates payloads, maps errors
│   │   └── cli.py
│   └── outbound/            # Concrete implementations of ports
│       ├── pg_order_repo.py # Maps SQL rows <-> domain entities (no ORM leak!)
│       ├── stripe_client.py # Retries, timeouts, translates SDK errors
│       └── system_clock.py
└── main.py                  # Composition Root: ONLY place wiring concrete adapters
```

### Pure Domain Core vs Adapters & Composition Root
```python
# domain/model.py — pure Python, deterministic, <1ms unit tests
from dataclasses import dataclass
from datetime import datetime

class OrderError(Exception): ...

@dataclass(frozen=True)
class Money:
    cents: int
    currency: str
    def __post_init__(self) -> None:
        if self.cents < 0:
            raise OrderError("negative money")

@dataclass
class Order:
    id: str
    total: Money
    status: str = "pending"

    def mark_paid(self, amount: Money, paid_at: datetime) -> None:
        if self.status != "pending":
            raise OrderError(f"cannot pay order in state {self.status}")
        if amount != self.total:
            raise OrderError("amount mismatch")
        self.status = "paid"

# ports/gateways.py — caller-owned narrow interfaces
from typing import Protocol

class Clock(Protocol):
    def now_utc(self) -> datetime: ...

class OrderRepo(Protocol):
    def get(self, order_id: str) -> Order | None: ...
    def save(self, order: Order) -> None: ...

# application/pay_order.py — depends only on domain + ports
def pay_order(order_id: str, paid: Money, repo: OrderRepo, clock: Clock) -> Order:
    order = repo.get(order_id)
    if order is None:
        raise OrderError("not found")
    order.mark_paid(paid, clock.now_utc())
    repo.save(order)
    return order

# main.py — Composition Root (no global service locator!)
def build_app(dsn: str) -> App:
    pool = PgPool(dsn)
    repo = PgOrderRepo(pool)
    clock = SystemClock()
    return App(pay_handler=lambda oid, amt: pay_order(oid, amt, repo, clock))
```

### Boundary Anti-Patterns & Verification
- **Anti-Pattern — Leaky ORM Entities:** Returning SQLAlchemy/Hibernate models directly from repos into HTTP routes triggers silent N+1 lazy loads outside sessions and couples business rules to column schemas. Always map DB rows to plain domain objects/DTOs at the repository boundary.
- **Anti-Pattern — Service Locator:** Calling `Container.resolve(PaymentGateway)` inside domain code hides dependencies and breaks static analysis. Inject explicit dependencies through constructors/function args at `main`.

Verify dependency direction automatically in CI:
```bash
# 1. Fail if domain/ imports web, SQL, or external SDKs
rg -n "^(import|from)\s+(fastapi|sqlalchemy|requests|httpx|boto3|psycopg)" src/*/domain/ && exit 1

# 2. Enforce layered imports in Python with import-linter (pyproject.toml)
# [tool.importlinter]
# root_package = "orders"
# [[tool.importlinter.contracts]]
# name = "Hexagonal layers"
# type = "layers"
# layers = ["orders.adapters", "orders.application", "orders.ports", "orders.domain"]
lint-imports
```

---

## 2. SOLID Principles (Pragmatic Application)

| Principle | Core Rule | Over-Engineering Trap |
|---|---|---|
| **SRP** | One coherent actor / reason to change per module | Splitting every single function into a 1-method class |
| **OCP** | Add behavior by registering new implementations, not editing central switches | Building plugin reflection registries for 2 static cases |
| **LSP** | Subtypes honor every caller precondition/postcondition and exception contract | Inheriting just to share helper code, then raising `NotImplementedError` |
| **ISP** | Keep interfaces narrow (`Reader`, `Clock`) so callers depend only on used methods | Creating a 1-to-1 interface for every concrete class blindly |
| **DIP** | High-level policy owns the `Protocol`; low-level I/O implements it | Injecting abstractions for pure deterministic math (`math.sqrt`) |

### Concrete Bad vs Good Mini-Examples

**SRP — Separate Business Policy from Transport/Persistence:**
```python
# BAD: Invoice mixes tax rules, SQL persistence, and SMTP email
class Invoice:
    def finalize(self, db, smtp):
        self.total = sum(i.price for i in self.items) * 1.08
        db.execute("UPDATE invoices SET total=? WHERE id=?", (self.total, self.id))
        smtp.send(self.email, f"Total: {self.total}")

# GOOD: Pure domain calculation; orchestration layer handles repo + mailer
class Invoice:
    def finalize(self, tax_rate: Decimal) -> Decimal: ...
```

**OCP — Extend via Registry/Protocol Instead of Multi-File `if/elif`:**
```python
# BAD: Every new export format requires editing export()
def export_report(data: list[dict], fmt: str) -> bytes:
    if fmt == "csv": ...
    elif fmt == "json": ...

# GOOD: Map format key -> small callable/Protocol
EXPORTERS: dict[str, Callable[[list[dict]], bytes]] = {"csv": to_csv, "json": to_json}
def export_report(data: list[dict], fmt: str) -> bytes:
    return EXPORTERS[fmt](data)
```

**LSP — Never Break Base Contract with Unsupported Methods:**
```python
# BAD: Caller expecting any Store to support put() crashes at runtime
class Store(Protocol):
    def get(self, k: str) -> bytes: ...
    def put(self, k: str, v: bytes) -> None: ...

class ReadOnlyArchive:
    def get(self, k: str) -> bytes: ...
    def put(self, k: str, v: bytes) -> None:
        raise NotImplementedError("read-only")  # LSP violation!

# GOOD: Split capabilities (ISP + LSP)
class Reader(Protocol):
    def get(self, k: str) -> bytes: ...
class Writer(Protocol):
    def put(self, k: str, v: bytes) -> None: ...
```

**ISP — Caller-Owned Narrow Interfaces:**
```python
# BAD: Auth token verifier forced to accept a 15-method UserDatabase
def verify_session(token: str, db: MegaUserDatabase) -> User: ...

# GOOD: Function declares only the 1 method it actually calls
class SessionLookup(Protocol):
    def find_active_user(self, user_id: str) -> User | None: ...
```

**DIP — Domain Defines Port; Adapter Depends on Domain:**
```python
# BAD: Core billing logic directly instantiates Stripe SDK
import stripe
def charge_user(uid: str, cents: int):
    return stripe.PaymentIntent.create(amount=cents, customer=uid)

# GOOD: Billing defines PaymentPort; StripeAdapter lives in adapters/outbound/
class PaymentPort(Protocol):
    def charge(self, uid: str, cents: int, idempotency_key: str) -> Receipt: ...
```

---

## 3. High-Value Design Patterns (When to Use & When NOT)

| Pattern | Use When | Do NOT Use When |
|---|---|---|
| **Strategy** | Runtime/config-selectable algorithms sharing signature (`PricingRule`, `Compressor`) | Only 1 algorithm exists or variants need wildly different parameters/outputs |
| **State Machine** | Entity has lifecycle rules & forbidden transitions (`Order`, `Job`, `Connection`) | 1–2 independent booleans with no invalid state combinations |
| **Adapter / Facade** | Wrapping messy vendor SDKs or simplifying a multi-step legacy subsystem | Pure pass-through wrapper adding indirection with zero translation |
| **Repository + UoW** | Complex aggregates needing invariant checks across atomic multi-repo writes | Simple CRUD scripts or read-heavy reporting/analytics queries |
| **Dependency Injection** | Isolating I/O, clocks, RNG, and external clients at composition root | Heavy reflection DI frameworks for a <20k LOC service |
| **Circuit Breaker + Bulkhead** | Calling unreliable network services to prevent cascade failures & pool starvation | In-process calls, or without timeouts (breaker without timeout still blocks!) |
| **Transactional Outbox** | Must atomically commit DB state AND reliably publish an event to a message broker | Best-effort logs/metrics where occasional event loss is acceptable |
| **Saga** | Multi-service or multi-DB workflow needing eventual consistency + rollback steps | Everything lives in one SQL DB (use a plain ACID transaction!) |
| **2PC (Two-Phase Commit)** | Tightly coupled homogeneous XA DBs needing strict atomic commit across shards | Cross-microservice/external HTTP APIs (blocks on coordinator crash, kills availability) |
| **CQRS** | Read shapes/scale diverge sharply from write invariants (search, feeds, dashboards) | Standard CRUD where read/write schemas match (doubles model/sync complexity) |

### Strategy & State Machine
Make illegal states unrepresentable with explicit transition tables (or Rust typestates):
```python
from enum import Enum, auto

class JobState(Enum):
    QUEUED = auto()
    RUNNING = auto()
    SUCCEEDED = auto()
    FAILED = auto()

ALLOWED_TRANSITIONS: dict[JobState, set[JobState]] = {
    JobState.QUEUED: {JobState.RUNNING, JobState.FAILED},
    JobState.RUNNING: {JobState.SUCCEEDED, JobState.FAILED},
    JobState.SUCCEEDED: set(),
    JobState.FAILED: {JobState.QUEUED},  # explicit retry path
}

def transition(current: JobState, target: JobState) -> JobState:
    if target not in ALLOWED_TRANSITIONS[current]:
        raise ValueError(f"illegal transition {current.name} -> {target.name}")
    return target
```

### Repository + Unit of Work
UoW binds a single DB transaction to one or more repositories so multi-entity invariants commit or roll back atomically:
```python
class UnitOfWork(Protocol):
    orders: OrderRepo
    ledger: LedgerRepo
    def __enter__(self) -> "UnitOfWork": ...
    def __exit__(self, exc_type, exc, tb) -> None: ...  # rollback on exc
    def commit(self) -> None: ...

def transfer_credit(uow_factory: Callable[[], UnitOfWork], src: str, dst: str, cents: int) -> None:
    with uow_factory() as uow:
        uow.ledger.debit(src, cents)
        uow.ledger.credit(dst, cents)
        uow.commit()  # atomic; auto-rollback if exception raised before commit()
```

### Circuit Breaker + Bulkhead
Always pair **timeouts** + **bounded concurrency (Bulkhead)** + **Circuit Breaker (Closed -> Open -> Half-Open)**:
```python
import asyncio, time

class CircuitOpenError(Exception): ...

class ResilientClient:
    def __init__(self, max_concurrent: int = 16, fail_threshold: int = 5, reset_sec: float = 15.0):
        self._bulkhead = asyncio.Semaphore(max_concurrent)  # isolates pool from other callers
        self._fails = 0
        self._fail_threshold = fail_threshold
        self._reset_sec = reset_sec
        self._opened_at: float | None = None

    async def call(self, fn):
        if self._opened_at is not None:
            if time.monotonic() - self._opened_at < self._reset_sec:
                raise CircuitOpenError("fast-fail: downstream open")
            # Half-open probe allowed; fall through with bulkhead
        async with self._bulkhead:
            try:
                async with asyncio.timeout(2.0):
                    res = await fn()
                self._fails = 0
                self._opened_at = None
                return res
            except Exception:
                self._fails += 1
                if self._fails >= self._fail_threshold:
                    self._opened_at = time.monotonic()
                raise
```
Use **fallback/degraded responses** or **429/503 load shedding** when `CircuitOpenError` triggers; add exponential backoff with full jitter ONLY for idempotent retries (`sleep = random.uniform(0, min(cap, base * 2 ** attempt))`).

### Transactional Outbox (Solving Dual-Write Races)
**Buggy dual-write:** `db.commit()` succeeds, then `kafka.publish()` crashes (lost event) — or `kafka.publish()` runs before `db.commit()`, which rolls back (phantom event).
**Fix:** Write the event row into an `outbox` table inside the **same ACID transaction**, then publish asynchronously:
```sql
-- 1. Inside business transaction:
BEGIN;
INSERT INTO orders (id, total_cents, status) VALUES ($1, $2, 'paid');
INSERT INTO outbox_events (id, aggregate_id, event_type, payload, created_at)
VALUES ($3, $1, 'order.paid', $4::jsonb, now());
COMMIT;

-- 2. Outbox relay worker (or Debezium CDC) polls safely across concurrent workers:
BEGIN;
SELECT id, event_type, payload
FROM outbox_events
WHERE published_at IS NULL
ORDER BY created_at
LIMIT 100
FOR UPDATE SKIP LOCKED;
-- Publish to broker, then: UPDATE outbox_events SET published_at = now() WHERE id = ANY($1);
COMMIT;
```
Outbox delivers **at-least-once**; consumers MUST deduplicate by `event_id` (store `processed_event_ids` in consumer DB transaction).

### Saga Pattern (vs 2PC)
- **Orchestration Saga:** Central state machine (`OrderSaga`) sends commands (`ReserveInventory` -> `ChargeCard` -> `ShipOrder`) and runs compensating commands (`ReleaseInventory`, `RefundCard`) in reverse order on failure. Best for complex flows (>3 steps) needing visibility.
- **Choreography Saga:** Services react to domain events (`OrderCreated` -> `InventoryReserved` -> `PaymentFailed` -> `ReleaseInventory`). Best for 2–3 steps; harder to trace globally.
- **Rule:** Compensations are **semantic undo operations** (e.g., refund/credit), NOT DB rollbacks, and MUST be idempotent and retryable because compensations themselves can transiently fail. Store saga step state in a durable DB before emitting external commands.

### CQRS (Command Query Responsibility Segregation)
Separate write commands (rich domain aggregates validating invariants in normalized tables) from read queries (plain SQL/views/Elasticsearch projections returning flat read DTOs directly without hydrating domain objects).
- **When NOT:** Simple CRUD where read/write DTOs are identical; CQRS adds projection lag and duplicate schemas for zero payoff.

---

## 4. Modular Monolith Design & Circular Dependencies

Start with a **modular monolith** before microservices: keep single-process calls and single-DB ACID simplicity while enforcing strict module boundaries so extracting a service later is mechanical.

### Bounded Context Boundaries
```text
src/
├── shared_kernel/        # Tiny immutable leaf: Money, TenantId, EventEnvelope (NO business logic)
├── billing/
│   ├── __init__.py       # PUBLIC API ONLY: BillingFacade, InvoiceDto, ChargeRequest
│   └── _internal/        # Private domain, SQL tables (billing_*), repos — NEVER imported outside!
└── orders/
    ├── __init__.py       # PUBLIC API ONLY
    └── _internal/        # Imports billing.__init__, NEVER billing._internal!
```
**Database Boundary Rule:** Each module owns its own tables/schema (`billing.invoices`, `orders.orders`). Never write cross-module SQL `JOIN`s or foreign keys into another module's private tables; read via the owning module's public facade or sync a local read projection via domain events.

### Breaking Circular Dependencies (3 Exact Fixes)
When `A` imports `B` and `B` imports `A`:
1. **Extract a Leaf (`shared_kernel`):** Move shared value types/IDs/exceptions used by both `A` and `B` into a third module `C` that depends on neither (`A -> C <- B`).
2. **Invert with a Port / Domain Event (DIP):** Keep `A -> B`, remove `B -> A` by having `B` define a `Protocol` or publish an event that `A` subscribes to at the composition root.
3. **Merge Fake Boundaries:** If `A` and `B` constantly mutate each other's internals, they are one cohesive module artificially split in two — merge them.

### Verification Commands
```bash
# Python: enforce module facade privacy + acyclic imports
# Check with import-linter (forbidden / independence contracts) or pydeps:
lint-imports
pydeps src/myapp --no-show --show-cycles

# TypeScript / JS: fail CI on circular imports
npx madge --circular --extensions ts,tsx src/

# Rust: split bounded contexts into workspace crates; Cargo guarantees an acyclic crate DAG
cargo check --workspace && cargo tree --duplicates
```
