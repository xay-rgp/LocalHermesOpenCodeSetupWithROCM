---
name: search-ir
description: Staff search, information retrieval, and text engine patterns — Okapi BM25 inverted indexes, positional phrase & boolean queries, BK-tree fuzzy matching, Myers diff/patch, C++20 Aho-Corasick automata, and XSS-safe HTML snippet highlighting.
---

# Staff Search, Information Retrieval & Text Engines

## Inverted Indexes & Okapi BM25
- **Deduplicate Query Terms:** Standard Okapi BM25 sums over *unique* query terms (`for term in set(tokenize(query, stopwords))`), NOT raw repeated query tokens — repeating `"search search"` must score identically to `"search"`.
- **Method/Attribute Shadowing:** Never name an instance attribute identically to a method (e.g., use `self._doc_count` when exposing `def doc_count(self) -> int`).
- **Deterministic Tie-Breaking:** Sort search results by `(-score, doc_id)` and guard `top_k` against `bool` (`isinstance(top_k, int) and not isinstance(top_k, bool)`).

## Positional Phrase & Boolean Query Engines
- **Token Positions vs Character Offsets:** Positional inverted indexes store 0-based *token indices* (`enumerate(re.findall(...))`), NOT character offsets (`m.start()`), so adjacent words satisfy `1 <= p_{i+1} - p_i <= slop + 1`.
- **Boolean Shunting-Yard Validation:** Treat unary `NOT` as right-associative (only pop strictly higher precedence operators so `NOT NOT x` works), reject odd quote counts (`expr.count('"') % 2 != 0`), and verify `len(eval_stack) == 1` after RPN evaluation.

## Aho-Corasick Multi-Pattern Automata (C++20)
- **Trie + BFS Failure + Dictionary Links:** Store nodes in a flat `std::vector<Node>` (`nodes_(1)` for root) so there is zero pointer chasing. When computing child `v` from `(u, c)` in BFS, walk `f = nodes_[u].fail` while `f != 0 && !nodes_[f].next.contains(c)`, set `fail(v)` to `nodes_[f].next[c]` (or `0`), and set `dict(v) = !nodes_[fail(v)].out.empty() ? fail(v) : nodes_[fail(v)].dict`. During `search()`, walk `d = cur; d != 0; d = nodes_[d].dict` to emit all overlapping matches `{i + 1 - pat_lens_[pid], pid}` in O(text_len + matches).

## XSS-Safe Search Snippet Highlighting
- **Exact Window Bounds:** Never compute `winStart = Math.floor(mid - maxLen/2)` and `winEnd = Math.ceil(mid + maxLen/2)` independently — when `mid` is a half-integer, `winEnd - winStart == maxLen + 1`! Instead compute `winStart = Math.max(0, Math.floor(mid - maxLen / 2)); winEnd = Math.min(text.length, winStart + maxLen); if (winEnd - winStart < maxLen) winStart = Math.max(0, winEnd - maxLen);`. Always HTML-escape `& < > " '` BEFORE wrapping match spans in `<mark>...</mark>`.
