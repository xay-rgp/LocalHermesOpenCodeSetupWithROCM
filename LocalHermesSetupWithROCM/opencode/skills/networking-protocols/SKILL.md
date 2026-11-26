---
name: networking-protocols
description: Staff networking, binary protocol, and wire framing patterns — LEB128/ZigZag varints, RFC 1035 DNS compression pointers, streaming RESP2 parsers, LPM IPv4/IPv6 CIDR routers, C++20 CRC32 binary frame decoders, and RFC 6455 WebSocket framing.
---

# Staff Networking, Binary Protocols & Wire Framing

## LEB128 / ZigZag Varints & Streaming TLV Framing
- **64-Bit Overflow Guard:** Unsigned LEB128 for `uint64` takes at most 10 bytes, and the 10th byte (`index == 9`) may only carry 1 payload bit (`(b & 0x7F) <= 1`). Raise `ValueError` on overflow or truncated varints.
- **ZigZag Signed Codec:** Encode signed 64-bit ints via `(n << 1) ^ (n >> 63)` (masked to 64 bits if needed) and decode via `(zz >> 1) ^ -(zz & 1)`.
- **Streaming Frame Buffers:** In `decode_frames(buf)`, distinguish *truncated* varints/payloads (return decoded frames + unconsumed `buf[start_pos:]`) from *malformed/overflow* varints (raise `ValueError` immediately).

## RFC 1035 DNS Wire Format & Compression Pointers
- **Pointer Cycle & Bounds Defense:** Track every visited offset in a `visited: set[int]` before jumping on a `0xC0` 2-byte compression pointer (`target = ((b0 & 0x3F) << 8) | b1`); reject `target >= len(packet)`, self/cyclic jumps, reserved `0x40`/`0x80` label prefixes, labels > 63 bytes, and total decoded length > 253.
- **Next-Offset Accounting:** Record `next_offset = ptr + 2` ONLY on the *first* compression pointer encountered (subsequent chained jumps do not advance the caller's stream offset).

## Streaming Protocol Parsers (RESP2 / Binary Frames)
- **Cursor-Based Recursive Parsing:** Always pass an explicit `pos: int` offset into `_parse_at(pos) -> tuple[Any, int] | None` (never parse from offset 0 inside recursive array/container parsers). Return `None` (NOT `(None, 0)`!) on incomplete frames so `feed()` stops cleanly without infinite loops.
- **Strict Framing Validation:** For length-prefixed bulk strings (`$n\r\n<n bytes>\r\n`), verify `buf[start + n : start + n + 2] == b"\r\n"` before accepting the payload.
- **C++20 Binary Frame Decoders:** Check `buffer_.size() >= HEADER_SIZE` (e.g., 8 bytes) first so `BadMagic` and `OversizedPayload` fail fast before waiting for `HEADER_SIZE + length + CRC_SIZE`. Compute CRC32 zero-copy over `std::span<const std::uint8_t>(buffer_.data(), HEADER_SIZE + length)` and always read the trailing checksum from `buffer_[HEADER_SIZE + length .. HEADER_SIZE + length + 3]` (never a hardcoded offset like `12`).

## RFC 6455 WebSocket Framing (Node.js)
- **Header & Offset Discipline:** Compute `headerLen = 2 + (len < 126 ? 0 : (len <= 65535 ? 2 : 8)) + (maskKey ? 4 : 0)` (only add 4 when `maskKey != null`). Always advance `offset += 2` after `writeUInt16BE` and `offset += 8` after `writeBigUInt64BE(BigInt(len), offset)`.
- **Streaming Unmasking & Remainder:** In `decodeFrames`, record `startPos = pos` before reading each frame, reject `(byte0 & 0x70) !== 0`, read the 4-byte `mask` *before* the payload when `masked` is set, convert 64-bit length via `Number(buf.readBigUInt64BE(pos))`, and on any incomplete header/mask/payload reset `pos = startPos` and break so `remainder = Buffer.from(buf.subarray(pos))` preserves the entire incomplete frame.
