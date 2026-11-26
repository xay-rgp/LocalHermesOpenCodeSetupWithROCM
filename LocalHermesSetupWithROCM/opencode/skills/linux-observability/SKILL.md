---
name: linux-observability
description: Staff Linux systems, IPC, and observability patterns — structured JSONL log routing & secret redaction, Prometheus latency histograms, 3-state circuit breakers, POSIX Bash process supervisors, non-blocking poll() pipe multiplexers, and W3C Trace Context propagation.
---

# Staff Linux Systems, IPC & Observability

## Structured Logging & Secret Redaction
- **Immutability & Deep Redaction:** Never mutate caller-supplied `fields` dicts/lists in place; recursively construct redacted copies matching sensitive key substrings case-insensitively (`password`, `passwd`, `secret`, `token`, `api_key`, `apikey`, `authorization`, `private_key`) and regex-scrubbing `Bearer <token>` inside strings.
- **Bounded Ring Buffers:** Use `collections.deque(maxlen=max_entries)` and increment `dropped_count` whenever `len(buf) == max_entries` before appending; serialize NDJSON with `sort_keys=True` for deterministic output.

## Latency Histograms & Prometheus 0.0.4 Exposition
- **Finite Numeric Validation:** Always check `isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)` for bucket bounds, observed values, and quantile `q` — `v > 0` alone passes `math.inf`!
- **Prometheus Escaping:** Escape `\` first, then `"` and `\n` in label values; emit `# HELP`, `# TYPE <name> histogram`, cumulative `<name>_bucket{...,le="<bound>"}` with `+Inf` last, and `<name>_sum`/`<name>_count` omitting `{}` when labels are empty.

## Bash Process Supervisors & Signal Traps
- **Safe Child Cleanup:** Under `set -euo pipefail`, always clear `CHILD_PID=""` immediately after `wait "$CHILD_PID"` finishes, and in `cleanup()` use `kill "$CHILD_PID" 2>/dev/null || true` (never `kill 0`, which kills the parent process group, and never `return 1` from an `EXIT` trap). Always quote `"$LOG_FILE"`, `"$PID_FILE"`, and `"${CMD_ARGS[@]}"` so paths with spaces work safely.

## Non-Blocking POSIX `poll()` Pipe Multiplexers (C++20)
- **Drain Before `POLLHUP`:** When a pipe writer closes immediately after writing, `poll()` sets `POLLIN | POLLHUP` simultaneously. Always drain `::read()` in a loop until `n == 0` (EOF) or `EAGAIN`/`EWOULDBLOCK` (retrying `EINTR`) BEFORE treating `POLLHUP` as EOF, flushing any non-empty trailing partial line before emitting the `eof = true` event.

## W3C Trace Context (`traceparent` / `tracestate`)
- **All-Zero Rule Scope:** In `00-<32-hex trace-id>-<16-hex parent-id>-<2-hex flags>`, `version` MUST be `"00"` and `flags` may legitimately be `"00"` — only `trace-id` and `parent-id` forbid all-zero hex strings!
- **Character-Class Escaping:** Put literal `-` at the end of regex character classes (e.g., `[a-z0-9_*/-]`) to avoid backslash escape-drift and `Range out of order` syntax errors.
