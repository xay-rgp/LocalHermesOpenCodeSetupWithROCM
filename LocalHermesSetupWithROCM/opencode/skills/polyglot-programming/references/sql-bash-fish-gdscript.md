# SQL, Bash, Fish, and GDScript 4 Reference

---

## 1. SQL (PostgreSQL-First Semantics + Standard SQL)

### CTEs & Recursive CTEs
- **Non-recursive CTE (`WITH`):** PostgreSQL 12+ inlines single-use non-materialized CTEs automatically; add `WITH cte AS MATERIALIZED (...)` only when forcing a single evaluation.
- **Recursive CTE:** Always enforce cycle detection and/or a depth bound on graph data so corrupted edges cannot loop forever.

```sql
WITH RECURSIVE tree AS (
    SELECT id, parent_id, name, 0 AS depth, ARRAY[id] AS path
    FROM categories WHERE parent_id IS NULL
    UNION ALL
    SELECT c.id, c.parent_id, c.name, t.depth + 1, t.path || c.id
    FROM categories c
    JOIN tree t ON c.parent_id = t.id
    WHERE NOT (c.id = ANY(t.path)) AND t.depth < 32
)
SELECT id, name, depth FROM tree;
```

### Window Functions & Frame Clauses
- `ROW_NUMBER()` assigns unique `1, 2, 3`; `RANK()` leaves gaps on ties (`1, 1, 3`); `DENSE_RANK()` has no gaps (`1, 1, 2`).
- `LAG(col, 1)` / `LEAD(col, 1)` inspect preceding/following rows without self-joins.
- **Critical frame-clause trap:** When `ORDER BY` is present, the default frame is `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` (groups all tied peers together and stops `LAST_VALUE` at the current row!). Use `ROWS` explicitly for physical running totals or full-partition bounds:

```sql
SELECT
    account_id,
    created_at,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id ORDER BY created_at, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_balance,
    LAST_VALUE(amount) OVER (
        PARTITION BY account_id ORDER BY created_at, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS latest_amount
FROM ledger;
```

### ACID Isolation Levels & Anomalies

| Isolation Level | Dirty Read | Non-Repeatable Read | Phantom Read | Write Skew (SI) |
|---|---|---|---|---|
| Read Uncommitted (PG treats as RC) | Possible* | Possible | Possible | Possible |
| Read Committed (PG default) | No | Possible | Possible | Possible |
| Repeatable Read (PG Snapshot Isolation) | No | No | No (PG) | **Possible!** |
| Serializable (SSI) | No | No | No | **No** (aborts w/ `40001`) |

- **Write skew under Snapshot Isolation (`REPEATABLE READ`):** Tx A and Tx B both read "2 doctors on call", Tx A removes Doctor 1, Tx B removes Doctor 2, and both commit (disjoint rows -> no write conflict -> invariant violated!). Fix with `SERIALIZABLE` (retry on SQLSTATE `40001`), `SELECT ... FOR UPDATE`, or a shared lock row.

### Indexing & Reading `EXPLAIN (ANALYZE, BUFFERS)`
- **Composite B-tree column order:** **Equality columns first, sort/range columns last.** `(tenant_id, status, created_at)` accelerates `WHERE tenant_id = $1 AND status = $2 AND created_at > $3`, and `WHERE tenant_id = $1`, but **not** `status = $2` alone.
- **Partial index:** `CREATE INDEX idx_jobs_ready ON jobs (run_at) WHERE status = 'queued';` — keeps index tiny by excluding finished rows.
- **Covering index:** `CREATE INDEX idx_users_email_cov ON users (email) INCLUDE (id, role);` — enables `Index Only Scan` without heap fetches (when autovacuum keeps visibility map updated).
- **GIN index:** Inverted index for `JSONB` (`@>`), array overlap (`&&`, `@>`), and `tsvector @@ tsquery`.
- **Reading `EXPLAIN (ANALYZE, BUFFERS)`:**
  - Compare `rows=` (estimate) vs `actual rows=` — >10x skew means stale stats (`ANALYZE tbl;`) or correlated columns (`CREATE STATISTICS`).
  - Watch `Rows Removed by Filter:` (missing/poorly ordered index), `Sort Method: external merge Disk` (exceeds `work_mem`), and `Buffers: shared read=` (cold disk reads) vs `hit=`.
  - Wrap write plans in `BEGIN; EXPLAIN (ANALYZE, BUFFERS) ...; ROLLBACK;`.
  - Keep predicates **sargable**: `created_at >= $1` uses an index; `DATE(created_at) = $1` or `col + 1 > 5` defeats B-tree index usage!

### Upsert (`ON CONFLICT`) & `SKIP LOCKED` Job Queue

```sql
-- Upsert: guard DO UPDATE with IS DISTINCT FROM to avoid writing identical dead tuples
INSERT INTO settings (key, val) VALUES ($1, $2)
ON CONFLICT (key) DO UPDATE SET val = EXCLUDED.val
WHERE settings.val IS DISTINCT FROM EXCLUDED.val;

-- Concurrent worker dequeue without lock contention or double-processing
WITH next_job AS (
    SELECT id FROM jobs
    WHERE status = 'queued' AND run_at <= now()
    ORDER BY run_at, id
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
UPDATE jobs j
SET status = 'running', started_at = now()
FROM next_job
WHERE j.id = next_job.id
RETURNING j.*;
```

---

## 2. Bash

### Strict Mode, Quoting, and `local` Trap
```bash
#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
```
- `-E`: inherit `ERR` trap in functions/subshells; `-e`: abort on non-zero exit; `-u`: error on unset variable; `-o pipefail`: fail if any command in a pipeline fails.
- **`set -e` traps:** Disabled inside `if`, `while`, `cmd || true`, and left of `&&`/`||`. Also `((count++))` returns exit status `1` when `count` starts at `0`, killing a `set -e` script! Use `count=$((count + 1))` or `((++count))`.
- **Always quote `"$var"`** and `"${arr[@]}"` to block word splitting and filename globbing.
- **Split `local` from command substitution:** `local out=$(failing_cmd)` returns `0` (exit status of `local`!), hiding failures from `set -e`:
  ```bash
  local out
  out=$(failing_cmd) # exit code preserved!
  ```
  (Same rule for `export` and `readonly`.)

### Arrays, `trap`/`mktemp` Cleanup, and Process Substitution
```bash
tmp_dir=$(mktemp -d)
cleanup() {
    local rc=$?
    rm -rf -- "$tmp_dir"
    exit "$rc"
}
trap 'exit 130' INT
trap 'exit 143' TERM
trap cleanup EXIT

# Never pack flags into a string; always use an array
flags=(--verbose --output "$tmp_dir/out.txt")
my_tool "${flags[@]}"

# Process substitution `<(...)` keeps `while` in the main shell (pipes run RHS in a subshell!)
count=0
while IFS= read -r line || [[ -n $line ]]; do
    count=$((count + 1))
done < <(grep -E 'ERROR' /var/log/app.log || true)
```
- **Filenames with spaces/newlines:** Use NUL delimiters: `find "$dir" -type f -print0 | while IFS= read -r -d '' f; do ...; done`.
- **Verify every script:** `bash -n script.sh && shellcheck script.sh`.

---

## 3. Fish Shell

### Scoping & Lists (1-Based Indexing!)
- **Variable scopes:** `set -l` (local to block/function), `set -g` (session global), `set -gx` (global + exported to subprocesses), `set -U` (universal, persisted across sessions in `~/.config/fish/fish_variables`—avoid `set -U PATH` in dotfiles; use `fish_add_path`). Always specify scope flags explicitly!
- **All variables are lists; zero word splitting:**
  - **1-based indexing:** `$arr[1]` is the first item; `$arr[-1]` is the last; `$arr[2..4]` slices; `count $arr` gives length. Indexing `0` yields nothing/error.
  - **Cartesian product:** `echo pre-$arr-post` expands per element; quote `"$arr"` to join with spaces or use `string join ',' -- $arr`.

### Builtins (`status`, `string`, `functions`, `--on-event`)
```fish
function deploy_file --argument-names src dst --description "Copy with check"
    if not test -f "$src"
        echo "missing: $src" >&2
        return 1
    end
    set -l clean (string trim -- "$dst")
    cp -- "$src" "$clean"
    return $status
end

# Event hooks: --on-event (fish_exit, fish_prompt) and --on-variable
function _on_exit --on-event fish_exit
    rm -f -- "$tmp_session_file"
end

function _auto_env --on-variable PWD
    status is-interactive; or return
    if test -f .envrc
        echo "Detected .envrc in $PWD"
    end
end
```
- **`status`:** Replaces `$?` (`$status`), checks `status is-interactive`, `status is-login`, `status filename`, `status dirname`. Pipeline statuses live in `$pipestatus`.
- **`string` builtin:** Fast in-process regex/text ops (`string match -r`, `string replace -a`, `string split`, `string trim`, `string escape`)—avoid spawning `sed`/`tr`/`cut`.
- **`functions` & `--on-event`:** `functions -q foo` checks existence; `functions foo` prints definition; `functions -e foo` deletes. Supported event hooks include `--on-event fish_exit`, `--on-signal SIGINT`, and `--on-variable VAR`.

### Key Differences from Bash
| Task | Bash | Fish |
|---|---|---|
| Export env var | `export FOO=bar` | `set -gx FOO bar` |
| One-shot env | `FOO=bar cmd` | `FOO=bar cmd` (3.1+) or `env FOO=bar cmd` |
| Command subst | `$(cmd)` | `(cmd)` (or `$(cmd)` in 3.4+, also inside `"..."`) |
| Last exit / pipe | `$?` / `${PIPESTATUS[@]}` | `$status` / `$pipestatus` |
| Boolean flow | `cmd1 && cmd2 \|\| cmd3` | `cmd1; and cmd2; or cmd3` (`&&`/`\|\|` work in 3.0+) |
| Heredocs | `cmd <<'EOF' ... EOF` | `printf '%s\n' ... \| cmd` (no heredocs) |
| Syntax check | `bash -n s.sh && shellcheck s.sh` | `fish -n s.fish` |

---

## 4. GDScript 4 Quick Primer

For full Godot 4 architecture, physics loops (`_physics_process`), scene trees, shaders, and 2D/3D workflows, load the **`godot-development`** skill.

- **Static typing & typed arrays:** Prefer explicit types everywhere for compile-time checks and VM speedup; avoid `Variant` surprises.
- **Signals & annotations:** Connect Callables directly (`hit.connect(_on_hit)` instead of string names); `@onready` resolves right before `_ready()` (still `null` in `_init()`!).
- **`await` safety:** Check `is_instance_valid(self)` after `await` on nodes that may be `queue_free()`d mid-coroutine.

```gdscript
class_name Player
extends CharacterBody2D

signal health_changed(current: int, maximum: int)

@export_range(1, 500) var max_hp: int = 100
@export var allies: Array[Node2D] = []
@onready var sprite: Sprite2D = $Sprite2D

var hp: int = 0

func _ready() -> void:
    hp = max_hp
    health_changed.emit(hp, max_hp)

func take_damage(amount: int) -> void:
    hp = maxi(0, hp - amount)
    health_changed.emit(hp, max_hp)
    if hp == 0:
        sprite.modulate = Color.RED
        await get_tree().create_timer(0.5).timeout
        if is_instance_valid(self):
            queue_free()
```
