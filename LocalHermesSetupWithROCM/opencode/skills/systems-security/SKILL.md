---
name: systems-security
description: Staff systems security, networking, and cryptography patterns — RFC 7519 HS256 JWT verification, hardened HTTP/1.1 request-smuggling defense, scrypt password hashing, SSRF IP/IPv6-mapped filtering, Node.js timingSafeEqual cookies/CSRF, and domain-separated Merkle audit logs.
---

# Staff Systems Security, Networking & Cryptography

## RFC 7519 HS256 JWT Verification
- **Algorithm Pinning:** Always enforce `header.get("alg") == "HS256"` strictly before trusting a signature; explicitly reject `alg: "none"`, `RS256`, or missing `alg`.
- **Constant-Time Verification & Claims:** Reject empty secrets and padded base64url segments (`=` in token), verify HMAC-SHA256 with `hmac.compare_digest`, and validate `exp`, `nbf`, `iss`, and `aud` against an explicit `now` timestamp with non-negative `leeway_s`.

## Password Hashing & Session Storage
- **Password Hashing (`scrypt`):** Never use MD5/SHA1/unsalted hashes; derive keys with `hashlib.scrypt(..., salt=secrets.token_bytes(16), n=16384, r=8, p=1, dklen=32)`, encode parameters + hex salt + hex key, and compare with `hmac.compare_digest`.
- **Hashed Session Tokens:** Generate tokens with `secrets.token_urlsafe(32)`, store only `hashlib.sha256(token.encode("utf-8")).hexdigest()` in the session store, and enforce explicit `now < expires_at` expiration.

## SSRF Defense & Narrow Exception Handling
- **IP Literal vs Domain Distinction:** Never wrap `raise SsrfError(...)` inside a broad `try: ip_address(host); ... except Exception: pass` (which swallows `SsrfError` because it subclasses `ValueError`!). Instead, parse ONLY `try: ip = ip_address(host)` / `except ValueError: ip = None`, then check `if ip is not None:` *outside* the `try` block.
- **IPv4-Mapped IPv6 & Resolved IPs:** Unwrap `if isinstance(ip, IPv6Address) and ip.ipv4_mapped: ip = ip.ipv4_mapped` and reject any IP that is not `is_global` (blocking loopback, RFC1918 private, `169.254.169.254` link-local, multicast, reserved, unspecified) for both IP literals and every entry in `resolved_ips`.

## Node.js `node:crypto` Constant-Time Verification
- **`timingSafeEqual` Length Guard:** `crypto.timingSafeEqual(bufA, bufB)` throws `RangeError` (`ERR_CRYPTO_TIMING_SAFE_EQUAL_LENGTH`) if `bufA.length !== bufB.length`. Always check `if (bufA.length !== bufB.length) return false;` before calling `crypto.timingSafeEqual(bufA, bufB)` in cookie/CSRF/HMAC verifiers.

## Tamper-Evident Merkle Audit Logs (RFC 6962)
- **Domain Separation:** Hash leaves with `SHA256(b"\x00" + data)` and internal nodes with `SHA256(b"\x01" + left + right)` to prevent second-preimage attacks where an internal node is forged as a leaf.
- **Bottom-Up Proof Reconstruction:** When collecting sibling hashes across `levels` (`levels[0]` = leaf hashes, `levels[-1]` = children of root), iterate `for level in levels:` bottom-up (NEVER `reversed(levels)`), updating `curr_idx //= 2` at each level, and verify final root equality with `hmac.compare_digest`.
