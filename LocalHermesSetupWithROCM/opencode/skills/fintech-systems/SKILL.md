---
name: fintech-systems
description: Staff-level financial systems engineering: exact integer minor-unit Money & Hamilton allocation, double-entry ledgers, Decimal amortization schedules, pre-trade risk guards, Rust limit order books, and idempotent payment state machines.
---

# Financial Systems, Ledgers & Matching Engines

## 1. Exact Money & Penny-Preserving Allocation
- **Never store money as IEEE 754 `float`:** Store exact integer minor units (`cents: int`) plus an uppercase 3-letter ASCII ISO currency code (`len(c) == 3 and c.isascii() and c.isalpha()`).
- **Strict Python type checks:** In Python, `isinstance(True, int)` is `True`! Always guard integer inputs with `isinstance(x, int) and not isinstance(x, bool)` and raise `TypeError` for `bool`/`float`/non-`int`.
- **Major-unit parsing:** Reject `float` and `bool` with `TypeError`; parse `int`/`str`/`Decimal` via `Decimal`, reject non-finite (`NaN`, `Infinity`) with `ValueError`, multiply by `100`, and quantize with `ROUND_HALF_EVEN` (banker's rounding).
- **Hamilton (Largest-Remainder) Allocation:**
  1. Validate `ratios` is non-empty (`ValueError`), every ratio is `int` and not `bool` (`TypeError`), every ratio `>= 0` (`ValueError`), and `total = sum(ratios) > 0` (`ValueError`).
  2. Split `mag = abs(self.cents)` via `q, rem = divmod(mag * r, total)`.
  3. Distribute `leftover = mag - sum(shares)` pennies (`+1` each) in descending `rem` order, breaking ties by earliest index (`key=lambda i: (-rems[i], i)`).
  4. Restore sign (`-s` if `self.cents < 0`) so `sum(part.cents for part in parts) == self.cents` is an unbreakable invariant.
- **Cross-currency safety:** Always reject cross-currency `+`, `-`, `<`, `<=`, `>`, `>=` with `ValueError`.

## 2. Double-Entry Accounting Ledger (`JournalLedger`)
- **Strict `Posting` validation in `@dataclass(frozen=True)`:**
  - Validate `isinstance(self.account, str) and bool(self.account)` (`ValueError`), `isinstance(self.side, str)` (`TypeError`), normalize `side = self.side.upper()` in `("DEBIT", "CREDIT")` (`ValueError`).
  - Guard `isinstance(self.amount, bool) or not isinstance(self.amount, int)` -> `TypeError`; `self.amount <= 0` -> `ValueError`.
  - Normalize `currency = self.currency.strip().upper()` (non-`str` -> `TypeError`, invalid 3-letter ASCII alpha -> `ValueError`) and persist via `object.__setattr__(self, "currency", currency)`.
- **Flexible sequence input:** In `post(entry_id, description, postings)`, accept any iterable (list, tuple, generator), convert `postings = tuple(postings)`, validate `len(postings) >= 2` (`ValueError`) and every element is `isinstance(p, Posting)` (`TypeError`).
- **Atomic & idempotent posting:**
  - Reject cross-currency postings and unbalanced entries (`sum(debits) != sum(credits)`) with `ValueError` BEFORE mutating state.
  - Deduplicate by `entry_id`: identical `(description, postings)` returns the existing `JournalEntry` without double-counting balances; colliding `entry_id` with different payload raises `ValueError`.
- **Consistent currency normalization:** Always normalize `currency.strip().upper()` in `balance()`, `trial_balance()`, and `is_balanced()`, and return `trial_balance()` sorted by account name.
