---
name: data-engineering
description: Staff data engineering, streaming, and compression patterns — Delta-of-Deltas + ZigZag + RLE columnar codecs, canonical Huffman bitstreams, event-time tumbling windows with watermarks, RFC 4180 streaming CSV + dead-letter queues, C++20 LZ77 overlapping-copy codecs, and zone-map predicate pushdown.
---

# Staff Data Engineering, Streaming & Compression

## Columnar Delta-of-Deltas, ZigZag & RLE Codecs
- **Delta-of-Deltas Recurrence:** Encode `v[0]`, then `d[1] = v[1] - v[0]`, then `dd[i] = (v[i] - v[i-1]) - d[i-1]` using ZigZag + unsigned LEB128 varints. On decode, ALWAYS maintain `curr_delta = prev_delta + zigzag_decode(dd_u)`, append `values[-1] + curr_delta`, and update `prev_delta = curr_delta` every iteration.
- **Strict Stream Validation:** After decoding `count` elements or `num_runs` runs, ALWAYS check `if offset != len(blob): raise ValueError("Trailing bytes")` and reject `bool` values (`isinstance(x, int) and not isinstance(x, bool)`).

## Canonical Huffman Bitstreams
- **Single-Symbol & Zero-Padding Guard:** Assign code length `1` (code `0`) when only 1 unique symbol exists. During decoding, break immediately as soon as `len(out) == orig_len` so trailing zero-padding bits in the final byte are never mistakenly decoded as extra `0`-code symbols.
- **Header Widths:** Use 2-byte `>H` for `num_symbols` (range `1..256` overflows a single byte) and share one `_build_canonical(lengths)` helper between encoder and decoder to check canonical code overflow (`code >= (1 << length)`).

## Streaming RFC 4180 CSV & Event-Time Windows
- **Character State Machine:** Never parse CSV with `.split("\n")` / `.split(",")`. Track `in_quotes`, decode `""` -> `"` inside quotes, preserve embedded `\n`/`\r\n` inside quotes, skip `\n` after `\r` outside quotes, and route unterminated quotes, column-count mismatches, and coercion errors to `dead_letter_rows` instead of crashing.
- **Event-Time Watermarks:** Advance `watermark = max(watermark, event_time - allowed_lateness)` monotonically, route events with `w_end <= watermark` to late-event side output, close windows when `w_end <= watermark`, and emit deterministically sorted by `(window_start, key)`.

## C++20 LZ77 Sliding-Window Compression
- **Overlapping Back-References (`dist < len`):** Always copy back-reference matches byte-by-byte (`output.push_back(output[output.size() - dist])`) rather than `std::copy` / `memcpy`, so RLE-like overlapping matches (`dist == 1, len == 200`) expand cleanly without UB or ASan errors. Validate `dist == 0 || dist > output.size() || len == 0` before copying and return `std::nullopt` on corrupt/truncated tokens.

## Row-Group Columnar Stores & Zone-Map Predicate Pushdown
- **Min/Max Zone-Map Pruning:** Track exact `(min, max)` per column per row group. Skip an entire row group before scanning any rows if: `eq(v)` has `v < min || v > max`, `gt(v)` has `max <= v`, `lt(v)` has `min >= v`, `between(lo, hi)` has `hi < min || lo > max`, or `in(vals)` has `!vals.some(v => v >= min && v <= max)`. Dictionary-encode string columns into `{ dict, codes }` to cut memory footprint.
