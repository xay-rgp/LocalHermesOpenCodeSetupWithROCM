# APIs, Databases, Security, and Observability Reference

## 1. API Design & Contracts

### REST Semantics & Status Codes
| Method | Safe | Idempotent | Expected Success / Concurrency Codes |
|---|---|---|---|
| `GET` / `HEAD` | Yes | Yes | `200 OK`, `304 Not Modified` (`ETag` / `If-None-Match`), `404` |
| `PUT` | No | Yes | `200`/`204` (replace full resource), `412 Precondition Failed` (`If-Match: "etag"`) |
| `DELETE` | No | Yes | `204 No Content` (or `404`; never fail retry inconsistently if already deleted) |
| `POST` | No | **Only via key** | `201 Created` + `Location: /v1/orders/{id}`, `202 Accepted` (async job), `409 Conflict` |
| `PATCH` | No | Depends | `200 OK`; prefer RFC 7396 Merge Patch or explicit command endpoint (`POST /orders/{id}/cancel`) |

- **Use `401 Unauthorized`** when credentials are missing/invalid; **`403 Forbidden`** when authenticated identity lacks permission (or **`404`** when hiding existence of private resources prevents enumeration).
- **Use `422 Unprocessable Content`** for semantic validation failures; **`400 Bad Request`** for malformed JSON/syntax; **`429 Too Many Requests`** + `Retry-After: <seconds>` when rate limited.

### Idempotent `POST` with `Idempotency-Key`
Prevent duplicate charges/orders on client network retries:
```python
# Atomic DB pattern: idempotency_keys(key PK, tenant_id, req_hash, status, response_json, created_at)
def handle_create_payment(tenant_id: str, key: str, body: bytes, db) -> tuple[int, dict]:
    req_hash = hashlib.sha256(body).hexdigest()
    # 1. Insert pending lock row (ON CONFLICT DO NOTHING)
    inserted = db.execute(
        "INSERT INTO idempotency_keys (key, tenant_id, req_hash) VALUES (%s, %s, %s) "
        "ON CONFLICT (key, tenant_id) DO NOTHING RETURNING key",
        (key, tenant_id, req_hash),
    ).fetchone()

    if not inserted:
        row = db.execute(
            "SELECT req_hash, status, response_json FROM idempotency_keys WHERE key=%s AND tenant_id=%s",
            (key, tenant_id),
        ).fetchone()
        if row.req_hash != req_hash:
            return 422, {"detail": "Idempotency-Key reused with different payload"}
        if row.status is None:
            return 409, {"detail": "Request with this Idempotency-Key is still in flight"}
        return row.status, row.response_json

    status, payload = execute_payment_transaction(body, db)
    db.execute(
        "UPDATE idempotency_keys SET status=%s, response_json=%s WHERE key=%s AND tenant_id=%s",
        (status, json.dumps(payload), key, tenant_id),
    )
    return status, payload
```
Expire keys after 24–72 hours via scheduled cleanup or TTL.

### RFC 9457 Problem Details (`application/problem+json`)
Standard error envelope across all endpoints (never expose stack traces or raw SQL errors in 5xx responses):
```json
{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Request validation failed",
  "status": 422,
  "detail": "2 fields failed validation.",
  "instance": "/v1/orders/ord_123",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "errors": [
    {"pointer": "#/items/0/quantity", "detail": "must be >= 1"}
  ]
}
```

### Cursor (Keyset) vs Offset Pagination
- **Avoid `OFFSET N`** on growing/large tables: DB still scans and discards `N` rows ($O(N)$), and concurrent inserts shift pages causing duplicate/skipped items.
- **Keyset / Cursor pagination ($O(\log N)$ with index):**
```sql
-- Requires composite index: CREATE INDEX idx_orders_page ON orders (tenant_id, created_at DESC, id DESC);
SELECT id, created_at, total_cents
FROM orders
WHERE tenant_id = $1
  AND (created_at, id) < ($2, $3)  -- decoded from opaque base64url cursor
ORDER BY created_at DESC, id DESC
LIMIT $4;  -- fetch limit + 1 to compute has_more without COUNT(*)!
```
Encode `(created_at, id)` into an opaque base64url token (optionally HMAC-signed) so clients never rely on internal sort columns. Offset is acceptable only for small, bounded admin tables (<10k rows) needing arbitrary page jumps.

### API Versioning & Rate Limiting
- **Versioning:** Favor additive non-breaking evolution (clients ignore unknown fields; new fields optional). Break contracts only on a new major version (`/v1/` -> `/v2/` or `Accept: application/vnd.api+json;version=2`) and emit `Deprecation` + `Sunset` HTTP headers before removal.
- **Rate Limiting (Token Bucket):** Each key stores `(tokens, last_refill_ms)` with capacity `burst` and refill `rate/sec`. Execute atomically in Redis via Lua script so concurrent checks cannot race; return `X-RateLimit-Remaining`, `X-RateLimit-Reset`, and `429` + `Retry-After`.

### Protocol Selection: REST vs gRPC vs GraphQL
| Criterion | REST + OpenAPI | gRPC + Protobuf | GraphQL |
|---|---|---|---|
| **Best Fit** | Public APIs, webhooks, HTTP cacheable CRUD | Internal low-latency RPC, streaming, strict polyglot schemas | Frontend BFF aggregating deeply nested resources |
| **Transport / Wire** | HTTP/1.1–3, JSON | HTTP/2, binary Protobuf | HTTP POST, JSON |
| **Strengths** | Universal tooling, CDN/ETag caching, human-readable | 5–10x smaller payloads, bi-di streaming, compile-time contracts | Eliminates over/under-fetching across mobile/web screens |
| **Pitfalls** | Chatty round-trips, ad-hoc schema drift without OpenAPI codegen | Poor browser support without proxy (gRPC-Web), harder curl debugging | N+1 query bombs (must use DataLoader), DoS via deep queries (enforce depth/cost limits + disable introspection in prod) |

---

## 2. Database Architecture

### 3NF vs Intentional Denormalization
- **Default to 3NF:** Every non-key attribute depends on the key, the whole key, and nothing but the key. Eliminates update/delete anomalies.
- **Denormalize ONLY for measured read bottlenecks or historical snapshots:**
  1. *Historical immutability:* Store `unit_price_cents` on `order_items` even though `products.price_cents` exists (future price changes must not rewrite past invoices!).
  2. *Read amplification:* Precomputed counters (`comment_count`), materialized views, or search projections — explicitly document the sync mechanism (same transaction vs outbox consumer) and reconciliation job.

### Indexing Mastery (PostgreSQL / SQL)
- **Composite Index Column Order:** **Equality predicates first, then sort/range columns.**
  - Query: `WHERE tenant_id = $1 AND status = 'open' AND created_at >= $2 ORDER BY created_at DESC`
  - Index: `CREATE INDEX idx_orders_t_s_c ON orders (tenant_id, status, created_at DESC);` (Leftmost prefix rule: also serves `(tenant_id)` and `(tenant_id, status)`).
- **Covering Indexes (`INCLUDE`):** Append non-filtered `SELECT` columns (`CREATE INDEX ... ON orders (tenant_id, status) INCLUDE (total_cents)`) to achieve an **Index-Only Scan** (`Heap Fetches: 0`).
- **Partial Indexes:** Index only the tiny hot subset:
  ```sql
  CREATE INDEX idx_jobs_pending ON jobs (run_at) WHERE status = 'pending';
  ```
- **Index Killers (Anti-Patterns):**
  - Wrapping indexed columns in functions: `WHERE LOWER(email) = $1` skips B-tree index on `email` -> create expression index `ON users (LOWER(email))` or use `citext`.
  - Leading wildcards `LIKE '%foo'` -> use trigram `GIN (col gin_trgm_ops)` or full-text `tsvector`.
  - Unindexed foreign keys -> cause sequential scans on child tables during parent `DELETE` or joins.
- **Verify Query Plans:**
  ```sql
  EXPLAIN (ANALYZE, BUFFERS) SELECT ...;
  -- Watch for: Seq Scan on large tables, huge Rows Removed by Filter, high shared read vs hit, Temp Read/Written (sort spill).
  ```

### Connection Pooling
Database backends consume ~5–10 MB RAM each and degrade sharply past ~2x–4x CPU core active threads due to lock/context-switch contention.
- **Rule of thumb for DB pool size:** `connections = (CPU_cores * 2) + effective_spindle_count` across ALL app replicas combined (typically 20–100 total active DB connections, NOT 200 per pod!).
- **App-side pool config:** Always set `max_size`, `acquire_timeout` (fail fast rather than queueing forever), `idle_timeout`, and `max_lifetime` (with jitter) to recycle stale TCP sockets.
- **External pooler (PgBouncer `transaction` mode):** Multiplexes thousands of client sockets onto dozens of Postgres backends. Caveat: avoid session-scoped features (`SET` without `LOCAL`, temp tables, `LISTEN/NOTIFY`, advisory session locks) in transaction mode.

### Zero-Downtime Expand-Contract Migrations
Never `RENAME COLUMN`, `DROP COLUMN`, or `ALTER TABLE ... ADD COLUMN ... NOT NULL DEFAULT (non-const)` in a single deploy while old and new app versions run simultaneously.

**Example: Safely renaming/migrating `full_name` -> `display_name NOT NULL`:**
1. **Expand (Migration 1 + Deploy App v2):**
   - `SET lock_timeout = '2s';` (fail fast instead of blocking behind long queries and queuing every subsequent `SELECT`!).
   - `ALTER TABLE users ADD COLUMN display_name TEXT;` (nullable, metadata-only instant in Postgres).
   - Deploy App v2: writes to **both** `full_name` and `display_name`; reads `COALESCE(display_name, full_name)`.
2. **Backfill (Out-of-band batched job):**
   - Update in small chunks (`LIMIT 5000` with brief pauses) to avoid table bloat, WAL spikes, and replication lag.
3. **Enforce Constraint Safely (Migration 2):**
   ```sql
   SET lock_timeout = '2s';
   -- Validates new writes immediately without scanning table under ACCESS EXCLUSIVE lock:
   ALTER TABLE users ADD CONSTRAINT chk_display_not_null CHECK (display_name IS NOT NULL) NOT VALID;
   -- Takes only SHARE UPDATE EXCLUSIVE (allows concurrent reads & writes):
   ALTER TABLE users VALIDATE CONSTRAINT chk_display_not_null;
   -- Indexes always built online:
   CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_display_name ON users (display_name);
   ```
4. **Contract (Deploy App v3 + Migration 3):**
   - App v3 stops reading/writing `full_name`. Only after v2 is 100% drained, `ALTER TABLE users DROP COLUMN full_name;`.

### Caching Patterns & Stampede Protection
- **Cache-Aside:** Read cache -> on miss, read DB -> write cache with TTL. On DB write: **invalidate (`DEL`)** after DB commit (updating cache blindly races with concurrent writes).
- **TTL Jitter:** `ttl = base_ttl + random.uniform(0, base_ttl * 0.2)` — prevents thousands of keys expiring simultaneously.
- **Singleflight (Stampede Protection):** Coalesce concurrent misses for the same hot key into **one** DB fetch:
```python
class Singleflight:
    def __init__(self) -> None:
        self._inflight: dict[str, asyncio.Future] = {}

    async def do(self, key: str, loader: Callable[[], Awaitable[Any]]) -> Any:
        if key in self._inflight:
            return await self._inflight[key]
        fut = asyncio.get_running_loop().create_future()
        self._inflight[key] = fut
        try:
            val = await loader()
            fut.set_result(val)
            return val
        except BaseException as exc:
            fut.set_exception(exc)
            raise
        finally:
            self._inflight.pop(key, None)
```
- **Cache Penetration Defense:** Cache `NOT_FOUND` sentinel values with a short TTL (e.g. 30–60s) or use a Bloom filter so attackers querying random nonexistent IDs don't hammer the DB.

---

## 3. Security Checklist (OWASP ASVS)

| Surface | Mandatory Control | Common Bug to Reject |
|---|---|---|
| **SQL / Command / Path** | Parameterized queries (`$1`/`?`), `subprocess.run(argv, shell=False)`, `path.resolve().is_relative_to(base)` | f-string SQL (`f"... {user_id}"`), `shell=True`, `os.path.join(base, user_path)` without traversal check |
| **AuthN (Passwords)** | **Argon2id** (`m=19456` KiB, `t=2`, `p=1` minimum) | Raw SHA-256, unsalted hashes, bcrypt truncating >72 bytes silently |
| **AuthN (Tokens)** | Short-lived JWT (5–15 min), pin allowed `algorithms=["EdDSA"]`/`["RS256"]`, validate `iss`/`aud`/`exp`; OR opaque server sessions | Accepting `alg: none` or header-driven algorithm, never-expiring JWTs |
| **Refresh Rotation** | One-time refresh tokens stored hashed (SHA-256) in DB; if a used token replays -> **revoke entire token family** | Stateless long-lived refresh tokens impossible to revoke on theft |
| **AuthZ (IDOR / BOLA)** | Enforce tenant/owner check inside query (`WHERE id = $1 AND org_id = $2`) + explicit DTO field allowlists | Checking `if not current_user` without checking resource ownership; passing raw JSON dict into ORM `**kwargs` (mass assignment) |
| **SSRF** | Allowlist scheme (`https`) + domain/port; resolve DNS -> reject loopback/RFC1918/link-local (`169.254.169.254`, `10/8`, `127/8`, `::1`, `fc00::/7`); connect to pinned IP & disable HTTP redirects | Validating URL string with regex before `requests.get(url)` (bypassed via HTTP 302 redirect or DNS rebinding!) |
| **CSRF / CORS** | Cookie auth: `HttpOnly; Secure; SameSite=Lax` + CSRF token on mutations; CORS: strict explicit origin allowlist | `Access-Control-Allow-Origin: <reflected Origin>` with `Allow-Credentials: true` |
| **Secret Comparison** | Constant-time equality: `hmac.compare_digest`, `crypto.timingSafeEqual`, `subtle::ConstantTimeEq` | `if signature == expected:` (timing side-channel) |
| **Secrets & Logs** | Env/KMS/Vault injection, redact `Authorization`/`password`/`token` in logs, scan commits (`gitleaks`) | Secrets in `.env` committed to Git, JWTs in URL query strings (`?token=...` leaks to access logs/Referer) |
| **Supply Chain** | Commit lockfiles with integrity hashes, verify licenses/CVEs in CI, minimize transitive deps | Floating `*`/`latest` ranges, `curl | bash` installers without checksum verification |

Verification commands:
```bash
# Python / Rust / Node vulnerability + secret hygiene gates
pip-audit --strict
cargo audit
npm audit --audit-level=high
gitleaks detect --source . --no-git
```

---

## 4. Observability (Logs, Metrics, Traces)

### Structured JSON Logging & Correlation IDs
Emit single-line JSON to `stdout` (let the runtime/collector handle shipping). Propagate `trace_id`, `span_id`, and `request_id` automatically via `contextvars` / `tracing::Span`:
```json
{
  "ts": "2026-11-21T23:10:04.182Z",
  "level": "error",
  "service": "orders-api",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "request_id": "req_9a81f",
  "event": "payment_gateway_timeout",
  "order_id": "ord_123",
  "duration_ms": 2004.2
}
```
Never log raw request bodies containing passwords, PII, session cookies, or full credit card numbers.

### RED & USE Metrics
- **RED (for Request-Driven Services):**
  - **R**ate: requests/sec (`http_requests_total`)
  - **E**rrors: failed requests/sec (`status=~"5.."`, distinct from client `4xx`)
  - **D**uration: latency histogram (`http_request_duration_seconds_bucket`) -> compute `p50`, `p95`, `p99` (never average latencies!).
- **USE (for Infrastructure/Pool Resources — CPU, RAM, Disk, DB Pool, Queues):**
  - **U**tilization: % busy (`pool_checked_out / pool_max_size`)
  - **S**aturation: queued work waiting (`pool_wait_queue_depth`, `pool_acquire_wait_seconds`)
  - **E**rrors: hardware/pool acquire timeout errors.
- **Cardinality Rule:** **NEVER** put unbounded values (`user_id`, `order_id`, `request_id`, raw URL paths with IDs) in Prometheus metric labels — use normalized route templates (`/v1/orders/{id}`) or put high-cardinality IDs in logs/traces instead.

### OpenTelemetry Distributed Tracing
- Propagate W3C `traceparent` / `tracestate` headers across HTTP, gRPC metadata, and Outbox/queue message headers.
- Record standard semantic attributes (`http.request.method`, `http.route`, `http.response.status_code`, `db.system`), call `span.record_exception(exc)` + `span.set_status(StatusCode.ERROR)` on failure, and configure head/tail sampling (100% of errors + slow tail, 1–10% of fast 2xx traffic) so trace storage scales cleanly.
